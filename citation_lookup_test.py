#!/usr/bin/env python
"""
Citation Lookup Test

This script asks for a citation and returns all available information from CourtListener,
saving it to a text file. It demonstrates the use of the CourtListenerAPI client.
"""

import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from courtlistener_api import CourtListenerAPI

# Load environment variables from .env file
load_dotenv()

def get_api_token():
    """Get the API token from the environment or prompt the user."""
    token = os.environ.get("COURT_LISTENER_TOKEN") or os.environ.get("COURTLISTENER_API_TOKEN")
    
    if not token:
        print("No API token found in environment variables.")
        print("Some lookups may fail without authentication.")
        
        use_token = input("Do you want to enter an API token? (y/n): ").lower().strip()
        if use_token == 'y':
            token = input("Enter your CourtListener API token: ").strip()
    
    return token

def format_json(data):
    """Format JSON data for better readability."""
    return json.dumps(data, indent=2, sort_keys=True)

def save_to_file(text, filename):
    """Save text content to a file."""
    with open(filename, 'w') as f:
        f.write(text)
    print(f"Results saved to {filename}")

def test_citation_formats(api, base_citation):
    """Test different citation formats to find one that works.
    
    Args:
        api: CourtListenerAPI instance
        base_citation: The original citation string
        
    Returns:
        Tuple of (successful_citation, response_or_error)
    """
    # Try different formats
    formats_to_try = [
        base_citation,  # Original format
        base_citation.replace(".", ""),  # Without periods
        " ".join(base_citation.split()),  # Normalized spacing
    ]
    
    # For reporter abbreviations like S.W.2d, also try S. W. 2d
    if "." in base_citation:
        spaced_format = base_citation.replace(".", ". ")
        formats_to_try.append(spaced_format)
    
    # Try each format
    for fmt in formats_to_try:
        try:
            print(f"Trying citation format: {fmt}")
            result = api.citation_lookup(fmt)
            if result and len(result) > 0:
                return fmt, result
        except requests.exceptions.RequestException as e:
            print(f"  Failed: {e}")
    
    return None, None

def main():
    """Main function."""
    # Get API token
    api_token = get_api_token()
    api = CourtListenerAPI(api_token)
    
    # Get citation from user
    citation = input("Enter citation (e.g., '410 U.S. 113'): ").strip()
    if not citation:
        print("No citation provided. Exiting.")
        return 1
    
    # Create output filename based on citation
    safe_citation = citation.replace(' ', '_').replace('/', '-').replace('\\', '-')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"citation_{safe_citation}_{timestamp}.txt"
    
    try:
        print(f"Looking up citation: {citation}")
        
        try:
            # Get citation metadata
            lookup_results = api.citation_lookup(citation)
        except requests.exceptions.HTTPError as e:
            if "400" in str(e):
                print("Bad Request error - the citation format may not be recognized.")
                print("Trying alternative formats...")
                
                valid_citation, lookup_results = test_citation_formats(api, citation)
                if not valid_citation:
                    print("All citation format attempts failed.")
                    return 1
                else:
                    print(f"Successfully found citation with format: {valid_citation}")
                    citation = valid_citation
            else:
                raise
        
        if not lookup_results or len(lookup_results) == 0:
            print(f"No results found for citation: {citation}")
            return 1
        
        # Get opinion text for the first result
        if lookup_results and isinstance(lookup_results, list) and len(lookup_results) > 0:
            match = lookup_results[0]
            opinion_id = match.get('id')
            
            if opinion_id:
                # Get the full opinion details
                try:
                    opinion = api.get_opinion(opinion_id)
                    
                    # Prepare the output
                    output = []
                    output.append(f"CITATION LOOKUP RESULTS - {citation}")
                    output.append("=" * 80)
                    output.append("")
                    
                    # Basic information
                    output.append("BASIC INFORMATION")
                    output.append("-" * 80)
                    output.append(f"Case Name:      {match.get('caseName', 'N/A')}")
                    output.append(f"Court:          {match.get('court', 'N/A')}")
                    output.append(f"Date Filed:     {match.get('dateFiled', 'N/A')}")
                    output.append(f"CourtListener URL: https://www.courtlistener.com{match.get('absolute_url', '')}")
                    
                    # Other citations
                    if 'citation' in match and match['citation']:
                        output.append("")
                        output.append("OTHER CITATIONS")
                        output.append("-" * 80)
                        for cite in match['citation']:
                            output.append(cite)
                    
                    # Raw metadata
                    output.append("")
                    output.append("RAW METADATA")
                    output.append("-" * 80)
                    output.append(format_json(match))
                    
                    # Full opinion details
                    output.append("")
                    output.append("FULL OPINION DETAILS")
                    output.append("-" * 80)
                    output.append(format_json(opinion))
                    
                    # Opinion text
                    opinion_text = opinion.get('plain_text', '')
                    if opinion_text:
                        output.append("")
                        output.append("OPINION TEXT")
                        output.append("-" * 80)
                        output.append(opinion_text)
                    
                    # Save everything to a file
                    save_to_file("\n".join(output), output_filename)
                    
                except Exception as e:
                    print(f"Error retrieving opinion details: {e}")
                    
                    # Save the metadata we have so far
                    output = []
                    output.append(f"CITATION LOOKUP RESULTS - {citation}")
                    output.append("=" * 80)
                    output.append("")
                    output.append("RAW METADATA")
                    output.append("-" * 80)
                    output.append(format_json(lookup_results))
                    save_to_file("\n".join(output), output_filename)
            else:
                # No opinion ID found, just save the lookup results
                output = []
                output.append(f"CITATION LOOKUP RESULTS - {citation}")
                output.append("=" * 80)
                output.append("")
                output.append("RAW METADATA")
                output.append("-" * 80)
                output.append(format_json(lookup_results))
                save_to_file("\n".join(output), output_filename)
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        
        if "401" in str(e) and "Unauthorized" in str(e):
            print("\nAuthentication Error: This API endpoint requires authentication.")
            print("Please set your API token in the COURTLISTENER_API_TOKEN environment variable:")
            print("export COURTLISTENER_API_TOKEN=your_token_here")
            print("\nTo get an API token, register at https://www.courtlistener.com/ and")
            print("go to https://www.courtlistener.com/profile/api/")
        
        return 1

if __name__ == "__main__":
    sys.exit(main()) 