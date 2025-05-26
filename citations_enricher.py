#!/usr/bin/env python
"""
Citations Enricher

This script uses the CourtListener API to enrich citation data extracted from legal briefs.
It takes citation data from a CSV file, looks up each citation in the CourtListener database,
and adds additional metadata from the API response.
"""

import csv
import json
import os
import sys
import argparse
from dotenv import load_dotenv
from courtlistener_api import CourtListenerAPI

# Load environment variables from .env file
load_dotenv()

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Enrich citation data using the CourtListener API")
    parser.add_argument("input_file", help="Input CSV file with citation data")
    parser.add_argument("output_file", help="Output CSV file for enriched data")
    parser.add_argument("--token", help="CourtListener API token (or use COURTLISTENER_API_TOKEN env var)")
    parser.add_argument("--log", help="Log file for failed lookups", default="lookup_errors.log")
    parser.add_argument("--citation-column", help="Name of the column with the citation", default="Citation")
    parser.add_argument("--case-column", help="Name of the column with the case name", default="Case Title")
    parser.add_argument("--include-text", action="store_true", help="Include opinion text in the output")
    parser.add_argument("--text-dir", help="Directory to save opinion text files (used with --include-text)", default="opinion_texts")
    return parser.parse_args()

def read_citations(input_file):
    """Read citation data from a CSV file.
    
    Args:
        input_file: Path to the input CSV file
        
    Returns:
        A list of dictionaries, each representing a citation
    """
    citations = []
    with open(input_file, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            citations.append(row)
    return citations

def format_citation(citation_str, case_name=""):
    """Format a citation string for lookup.
    
    Args:
        citation_str: The raw citation string
        case_name: The case name (optional)
        
    Returns:
        A formatted citation string suitable for lookup
    """
    # Skip empty citations
    if not citation_str or citation_str.strip() == "":
        return None
    
    # Skip citations that are just case numbers (not formal citations)
    if citation_str.startswith("No."):
        return None
    
    # For some citation formats, we need to add the case name
    if case_name and "v." in case_name and not citation_str.startswith(case_name):
        return f"{case_name}, {citation_str}"
    
    return citation_str

def enrich_citation(api, citation_row, citation_column, case_column, include_text=False, text_dir=None):
    """Enrich a citation with data from the CourtListener API.
    
    Args:
        api: CourtListenerAPI instance
        citation_row: Dictionary containing citation data
        citation_column: Name of the column with the citation
        case_column: Name of the column with the case name
        include_text: Whether to include opinion text
        text_dir: Directory to save opinion text files
        
    Returns:
        Enriched citation data dictionary, or None if lookup failed
    """
    # Get the citation string and case name
    citation_str = citation_row.get(citation_column)
    case_name = citation_row.get(case_column, "")
    
    # Format the citation for lookup
    formatted_citation = format_citation(citation_str, case_name)
    if not formatted_citation:
        return None
    
    try:
        print(f"Looking up citation: {formatted_citation}")
        
        if include_text:
            # Use the method that retrieves both metadata and text
            match, text = api.get_opinion_text_by_citation(formatted_citation)
            
            if not match:
                return None
                
            # Add CourtListener data to our citation
            citation_row['cl_opinion_id'] = match.get('id')
            citation_row['cl_case_name'] = match.get('caseName')
            citation_row['cl_court'] = match.get('court')
            citation_row['cl_date_filed'] = match.get('dateFiled')
            citation_row['cl_absolute_url'] = match.get('absolute_url')
            
            # Add any other citation forms found
            if 'citation' in match and match['citation']:
                citation_row['cl_other_citations'] = '; '.join(match['citation'])
            
            # Handle the text
            if text and text_dir:
                # Create directory if it doesn't exist
                os.makedirs(text_dir, exist_ok=True)
                
                # Create a filename based on the citation
                safe_citation = formatted_citation.replace(' ', '_').replace('/', '-').replace('\\', '-')
                filename = f"{safe_citation}.txt"
                
                # Write the text to a file
                with open(filename, 'w') as f:
                    f.write(text)
                
                # Add the file path to the citation data
                citation_row['cl_text_file'] = filename
                
                # Add a preview of the text (first 300 characters)
                if text:
                    citation_row['cl_text_preview'] = text[:300] + ('...' if len(text) > 300 else '')
            
            return citation_row
        else:
            # Use the original method that just retrieves metadata
            lookup_result = api.citation_lookup(formatted_citation)
            
            # Check if we got a valid result
            if lookup_result and isinstance(lookup_result, list) and len(lookup_result) > 0:
                # Get the first match (most relevant)
                match = lookup_result[0]
                
                # Add CourtListener data to our citation
                citation_row['cl_opinion_id'] = match.get('id')
                citation_row['cl_case_name'] = match.get('caseName')
                citation_row['cl_court'] = match.get('court')
                citation_row['cl_date_filed'] = match.get('dateFiled')
                citation_row['cl_absolute_url'] = match.get('absolute_url')
                
                # Add any other citation forms found
                if 'citation' in match and match['citation']:
                    citation_row['cl_other_citations'] = '; '.join(match['citation'])
                
                return citation_row
    except Exception as e:
        print(f"Error looking up citation '{formatted_citation}': {e}")
    
    return None

def write_enriched_citations(citations, output_file):
    """Write enriched citation data to a CSV file.
    
    Args:
        citations: List of enriched citation dictionaries
        output_file: Path to the output CSV file
    """
    if not citations:
        print("No enriched citations to write.")
        return
    
    # Get all fieldnames from citations (including the new enriched fields)
    fieldnames = set()
    for citation in citations:
        fieldnames.update(citation.keys())
    fieldnames = sorted(list(fieldnames))
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(citations)

def main():
    """Main function."""
    args = parse_args()
    
    # Get API token from args or environment variable
    api_token = args.token or os.environ.get("COURT_LISTENER_TOKEN") or os.environ.get("COURTLISTENER_API_TOKEN")
    if not api_token:
        print("Warning: No API token provided. Some lookups may fail.")
        print("Set the COURT_LISTENER_TOKEN environment variable or use --token.")
    
    # Initialize API client
    api = CourtListenerAPI(api_token)
    
    # Read citations from input file
    try:
        citations = read_citations(args.input_file)
        print(f"Read {len(citations)} citations from {args.input_file}")
    except Exception as e:
        print(f"Error reading input file: {e}")
        return 1
    
    # Enrich citations
    enriched_citations = []
    errors = []
    
    for i, citation in enumerate(citations):
        print(f"Processing citation {i+1}/{len(citations)}: {citation.get(args.citation_column, 'N/A')}")
        enriched = enrich_citation(api, citation, args.citation_column, args.case_column, 
                                args.include_text, args.text_dir)
        
        if enriched:
            enriched_citations.append(enriched)
        else:
            errors.append(citation)
    
    # Write enriched citations to output file
    try:
        write_enriched_citations(enriched_citations, args.output_file)
        print(f"Wrote {len(enriched_citations)} enriched citations to {args.output_file}")
        
        if args.include_text:
            print(f"Opinion texts saved to {args.text_dir}/")
    except Exception as e:
        print(f"Error writing output file: {e}")
        return 1
    
    # Write errors to log file
    if errors:
        try:
            with open(args.log, 'w') as f:
                json.dump(errors, f, indent=2)
            print(f"Wrote {len(errors)} failed lookups to {args.log}")
        except Exception as e:
            print(f"Error writing log file: {e}")
    
    print(f"Successfully enriched {len(enriched_citations)} out of {len(citations)} citations")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 