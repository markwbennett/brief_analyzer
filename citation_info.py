#!/usr/bin/env python
"""
Citation Info

A command-line tool to retrieve and save all available information about a legal citation from CourtListener.
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv
from courtlistener_api import CourtListenerAPI

# Load environment variables from .env file
load_dotenv()

def format_json(data):
    """Format JSON data for better readability."""
    return json.dumps(data, indent=2, sort_keys=True)

def save_to_file(text, filename):
    """Save text content to a file."""
    with open(filename, 'w') as f:
        f.write(text)
    print(f"Results saved to {filename}")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Get information about a legal citation from CourtListener")
    parser.add_argument("citation", help="The citation to look up (e.g., '410 U.S. 113')")
    parser.add_argument("--output", "-o", help="Output file name (default: auto-generated based on citation)")
    parser.add_argument("--token", "-t", help="CourtListener API token (or use COURTLISTENER_API_TOKEN env var)")
    parser.add_argument("--include-text", "-i", action="store_true", help="Include opinion text in output")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="Output format (default: text)")
    parser.add_argument("--debug", "-d", action="store_true", help="Show debug information")
    parser.add_argument("--try-alternatives", "-a", action="store_true", help="Try alternative citation formats if lookup fails")
    return parser.parse_args()

def test_citation_formats(api, base_citation, debug=False):
    """Test different citation formats to find one that works.
    
    Args:
        api: CourtListenerAPI instance
        base_citation: The original citation string
        debug: Whether to print debug information
        
    Returns:
        Tuple of (successful_citation, response_or_error)
    """
    # Try different formats
    formats_to_try = [
        base_citation,  # Original format
        base_citation.replace(".", ""),  # Without periods
        " ".join(base_citation.split()),  # Normalized spacing
    ]
    
    # Try URL format (e.g., U.S./410/113)
    parts = base_citation.split()
    if len(parts) >= 3:
        # Handle common reporter formats like "347 U.S. 483"
        if parts[1].upper() in ["U.S.", "US", "F.", "F.2D", "F.3D", "S.CT.", "L.ED.", "L.ED.2D"]:
            url_format = f"{parts[1].replace('.', '')}/{parts[0]}/{parts[2].replace('.', '')}"
            formats_to_try.append(url_format)
    
    # For reporter abbreviations like S.W.2d, also try S. W. 2d
    if "." in base_citation:
        spaced_format = base_citation.replace(".", ". ")
        formats_to_try.append(spaced_format)
    
    # Try with court identifier (for state reporters)
    if base_citation.count(" ") >= 2:
        parts = base_citation.split()
        if len(parts) >= 3 and parts[1].upper() in ["S.W.", "S.W.2D", "S.W.3D", "A.", "P.", "P.2D", "P.3D", "N.E.", "N.W.", "SO.", "SO.2D", "SO.3D"]:
            # Try adding state identifiers for common reporters
            reporter_map = {
                "S.W.": ["Tex.", "Ky.", "Mo.", "Tenn.", "Ark."],
                "S.W.2D": ["Tex.", "Ky.", "Mo.", "Tenn.", "Ark."],
                "S.W.3D": ["Tex.", "Ky.", "Mo.", "Tenn.", "Ark."],
                "A.": ["Md.", "N.J.", "Pa.", "Vt."],
                "P.": ["Cal.", "Colo.", "Kan.", "Or.", "Wash."],
                "P.2D": ["Cal.", "Colo.", "Kan.", "Or.", "Wash."],
                "P.3D": ["Cal.", "Colo.", "Kan.", "Or.", "Wash."],
                "N.E.": ["Ill.", "Ind.", "Mass.", "N.Y.", "Ohio"],
                "N.W.": ["Iowa", "Mich.", "Minn.", "Neb.", "Wis."],
                "SO.": ["Ala.", "Fla.", "Miss."],
                "SO.2D": ["Ala.", "Fla.", "Miss."],
                "SO.3D": ["Ala.", "Fla.", "Miss."]
            }
            
            reporter = parts[1].upper()
            if reporter in reporter_map:
                for state in reporter_map[reporter]:
                    state_citation = f"{parts[0]} {parts[1]} {parts[2]} ({state})"
                    formats_to_try.append(state_citation)
    
    # Try using direct URL format from the example in the documentation
    # Example: /c/U.S./410/113/ for Roe v. Wade
    if len(parts) >= 3 and parts[1].upper() in ["U.S.", "US"]:
        volume = parts[0]
        reporter = "U.S."
        page = parts[2]
        direct_url = f"/c/{reporter}/{volume}/{page}/"
        
        # Try making a request to this URL directly
        if debug:
            print(f"Trying direct URL: {direct_url}")
        try:
            # Use a modified approach for direct URL
            base_url = "https://www.courtlistener.com"
            response = api.session.get(f"{base_url}{direct_url}")
            response.raise_for_status()
            # If we get here, the direct URL worked
            if debug:
                print(f"Direct URL successful: {direct_url}")
            # Now try the citation lookup again
            return base_citation, api.citation_lookup(base_citation)
        except Exception as e:
            if debug:
                print(f"  Direct URL failed: {e}")
    
    # Try each format with the API
    for fmt in formats_to_try:
        try:
            if debug:
                print(f"Trying citation format: {fmt}")
            result = api.citation_lookup(fmt)
            if result and len(result) > 0:
                return fmt, result
        except requests.exceptions.RequestException as e:
            if debug:
                print(f"  Failed: {e}")
    
    return None, None

def get_citation_info(api, citation, include_text=False, debug=False, try_alternatives=False):
    """Get all available information about a citation.
    
    Args:
        api: CourtListenerAPI instance
        citation: The citation to look up
        include_text: Whether to include opinion text
        debug: Whether to print debug information
        try_alternatives: Whether to try alternative citation formats
        
    Returns:
        A dictionary with all available information
    """
    result = {
        "citation": citation,
        "lookup_results": None,
        "opinion": None,
        "opinion_text": None,
        "error": None
    }
    
    try:
        # Get citation metadata
        try:
            lookup_results = api.citation_lookup(citation)
            result["lookup_results"] = lookup_results
        except requests.exceptions.HTTPError as e:
            if "400" in str(e) and try_alternatives:
                if debug:
                    print("Bad Request error - trying alternative citation formats")
                valid_citation, lookup_results = test_citation_formats(api, citation, debug)
                if valid_citation:
                    result["citation"] = valid_citation  # Update with working citation format
                    result["lookup_results"] = lookup_results
                    if debug:
                        print(f"Successfully found citation with format: {valid_citation}")
                else:
                    result["error"] = f"Citation format not recognized: {citation}"
                    return result
            else:
                result["error"] = str(e)
                return result
        
        if not lookup_results or len(lookup_results) == 0:
            result["error"] = f"No results found for citation: {citation}"
            return result
        
        # Get opinion details and text
        if lookup_results and isinstance(lookup_results, list) and len(lookup_results) > 0:
            match = lookup_results[0]
            opinion_id = match.get('id')
            
            if opinion_id and include_text:
                # Get the full opinion details
                opinion = api.get_opinion(opinion_id)
                result["opinion"] = opinion
                
                # Get opinion text
                if opinion and "plain_text" in opinion:
                    result["opinion_text"] = opinion.get("plain_text")
    
    except Exception as e:
        result["error"] = str(e)
    
    return result

def format_as_text(info):
    """Format citation information as text.
    
    Args:
        info: Dictionary with citation information
        
    Returns:
        Formatted text
    """
    output = []
    citation = info["citation"]
    
    output.append(f"CITATION LOOKUP RESULTS - {citation}")
    output.append("=" * 80)
    output.append("")
    
    if info["error"]:
        output.append(f"ERROR: {info['error']}")
        output.append("")
    
    if info["lookup_results"] and len(info["lookup_results"]) > 0:
        match = info["lookup_results"][0]
        
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
        if info["opinion"]:
            output.append("")
            output.append("FULL OPINION DETAILS")
            output.append("-" * 80)
            output.append(format_json(info["opinion"]))
        
        # Opinion text
        if info["opinion_text"]:
            output.append("")
            output.append("OPINION TEXT")
            output.append("-" * 80)
            output.append(info["opinion_text"])
    
    return "\n".join(output)

def main():
    """Main function."""
    args = parse_args()
    
    # Get API token from args or environment variable
    api_token = args.token or os.environ.get("COURT_LISTENER_TOKEN") or os.environ.get("COURTLISTENER_API_TOKEN")
    if not api_token:
        print("Warning: No API token provided. Some lookups may fail.")
        print("Set the COURT_LISTENER_TOKEN environment variable or use --token.")
    
    api = CourtListenerAPI(api_token)
    citation = args.citation
    
    # Generate output filename if not provided
    if args.output:
        output_filename = args.output
    else:
        safe_citation = citation.replace(' ', '_').replace('/', '-').replace('\\', '-')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"citation_{safe_citation}_{timestamp}.{args.format}"
    
    # Get citation information
    print(f"Looking up citation: {citation}")
    info = get_citation_info(api, citation, include_text=args.include_text, 
                        debug=args.debug, try_alternatives=args.try_alternatives)
    
    # Format and save results
    if args.format == "json":
        # Remove opinion text if it's very large to avoid overwhelming the JSON output
        if info["opinion_text"] and len(info["opinion_text"]) > 10000:
            info["opinion_text"] = info["opinion_text"][:10000] + "... [truncated]"
        
        output = json.dumps(info, indent=2)
        save_to_file(output, output_filename)
    else:
        output = format_as_text(info)
        save_to_file(output, output_filename)
    
    # Report any errors
    if info["error"]:
        print(f"Error: {info['error']}")
        
        if "401" in info["error"] and "Unauthorized" in info["error"]:
            print("\nAuthentication Error: This API endpoint requires authentication.")
            print("Please set your API token in the COURTLISTENER_API_TOKEN environment variable:")
            print("export COURTLISTENER_API_TOKEN=your_token_here")
            print("\nTo get an API token, register at https://www.courtlistener.com/ and")
            print("go to https://www.courtlistener.com/profile/api/")
        elif "400" in info["error"] and "Bad Request" in info["error"]:
            print("\nBad Request Error: The citation format may not be supported.")
            print("Try using the --try-alternatives flag to attempt different citation formats.")
            print("Common formats for state reporters should include the state abbreviation.")
            print("Examples: ")
            print("  - '698 S.W.2d 362 (Tex.)' instead of '698 S.W.2d 362'")
            print("  - '543 N.E.2d 49 (Ill.)' instead of '543 N.E.2d 49'")
            
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 