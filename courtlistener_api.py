#!/!/./.venv/bin/python
"""
CourtListener API Client

This module provides a Python client for the CourtListener API.
"""

import requests
import json
import sys
import os
import argparse
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API token from environment
api_token = os.getenv('COURT_LISTENER_TOKEN')
if not api_token:
    raise ValueError("COURT_LISTENER_TOKEN not found in .env file")

# Basic authentication with token for downloading case text
headers = {'Authorization': f'Token {api_token}'}

class CourtListenerAPI:
    """Client for interacting with the CourtListener API."""
    
    BASE_URL = "https://www.courtlistener.com/api/rest/v4/"
    WEB_URL = "https://www.courtlistener.com"
    
    def __init__(self, api_token=None):
        """Initialize the API client.
        
        Args:
            api_token: Optional API token for authenticated requests
        """
        self.api_token = api_token
        self.session = requests.Session()
        if api_token:
            self.session.headers.update({"Authorization": f"Token {api_token}"})
    
    def get_endpoints(self):
        """Get a list of available API endpoints."""
        response = self.session.get(self.BASE_URL)
        response.raise_for_status()
        return response.json()
    
    def search_opinions(self, query, page=1, **kwargs):
        """Search for opinions using the provided query.
        
        Args:
            query: The search query
            page: The page number for pagination
            **kwargs: Additional search parameters
        
        Returns:
            The search results as a dictionary
        """
        params = {"q": query, "page": page, **kwargs}
        response = self.session.get(f"{self.BASE_URL}search/", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_all_search_results(self, query, max_pages=10, **kwargs):
        """Get all search results, handling pagination automatically.
        
        Args:
            query: The search query
            max_pages: Maximum number of pages to retrieve
            **kwargs: Additional search parameters
        
        Returns:
            A list of all search result items
        """
        results = []
        current_page = 1
        
        while True:
            response = self.search_opinions(query, page=current_page, **kwargs)
            results.extend(response.get("results", []))
            
            # Check if there are more pages
            if not response.get("next") or current_page >= max_pages:
                break
                
            current_page += 1
            print(f"Retrieved page {current_page-1}, continuing to next page...")
        
        return results
    
    def get_opinion(self, opinion_id):
        """Get details for a specific opinion.
        
        Args:
            opinion_id: The ID of the opinion
            
        Returns:
            The opinion details as a dictionary
        """
        response = self.session.get(f"{self.BASE_URL}opinions/{opinion_id}/")
        response.raise_for_status()
        return response.json()
    
    def get_docket(self, docket_id):
        """Get details for a specific docket.
        
        Args:
            docket_id: The ID of the docket
            
        Returns:
            The docket details as a dictionary
        """
        response = self.session.get(f"{self.BASE_URL}dockets/{docket_id}/")
        response.raise_for_status()
        return response.json()
    
    def citation_lookup(self, citation):
        """Look up a case by citation.
        
        Args:
            citation: The citation to look up (e.g., "410 U.S. 113")
            
        Returns:
            The citation lookup results as a dictionary
        """
        response = self.session.get(f"{self.BASE_URL}citation-lookup/?citation={citation}")
        response.raise_for_status()
        return response.json()
    
    def get_opinion_text_by_citation(self, citation):
        """Look up a case by citation and retrieve the opinion text.
        
        Args:
            citation: The citation to look up (e.g., "410 U.S. 113")
            
        Returns:
            A tuple of (opinion_details, opinion_text) if found, or (None, None) if not found
        """
        # First look up the citation to get the opinion ID
        lookup_results = self.citation_lookup(citation)
        
        if not lookup_results or not isinstance(lookup_results, list) or len(lookup_results) == 0:
            return None, None
        
        # Get the first (most relevant) result
        match = lookup_results[0]
        opinion_id = match.get('id')
        
        if not opinion_id:
            return match, None
        
        # Get the full opinion details
        opinion = self.get_opinion(opinion_id)
        
        # Return both the metadata and the text
        return match, opinion.get('plain_text', '')
    
    def get_opinion_by_url(self, reporter, volume, page):
        """Get an opinion using the direct citation URL format.
        
        This uses the format mentioned in the documentation:
        /c/U.S./410/113/ which will take you straight to Roe v. Wade
        
        Args:
            reporter: The reporter (e.g., "U.S.")
            volume: The volume number (e.g., "410")
            page: The page number (e.g., "113")
            
        Returns:
            The opinion data if found, or raises an exception if not found
        """
        url = f"{self.WEB_URL}/c/{reporter}/{volume}/{page}/"
        response = self.session.get(url, allow_redirects=True)
        response.raise_for_status()
        
        # This returns an HTML page, so we need to extract the opinion ID
        # from the URL we're redirected to
        final_url = response.url
        if "/opinion/" in final_url:
            # Extract the opinion ID from the URL path
            path_parts = final_url.split("/")
            try:
                opinion_id = None
                for i, part in enumerate(path_parts):
                    if part == "opinion" and i+1 < len(path_parts):
                        opinion_id = path_parts[i+1]
                        break
                
                if opinion_id and opinion_id.isdigit():
                    try:
                        # Now get the full opinion details using the ID
                        return self.get_opinion(opinion_id)
                    except requests.exceptions.HTTPError as e:
                        if "403" in str(e) and "Forbidden" in str(e):
                            # If we get a 403 error, we can still return basic information
                            # from the URL and final redirect
                            # Extract case name from URL
                            case_name = None
                            if len(path_parts) > i+2:
                                case_name_slug = path_parts[i+2]
                                case_name = case_name_slug.replace('-', ' ').title()
                            
                            return {
                                "id": opinion_id,
                                "caseName": case_name,
                                "citation": f"{volume} {reporter} {page}",
                                "absolute_url": final_url.replace(self.WEB_URL, ""),
                                "note": "Limited information available due to access restrictions."
                            }
                        else:
                            raise
            except:
                pass
        
        raise Exception(f"Failed to extract opinion ID from URL: {final_url}")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Command line client for the CourtListener API")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Endpoints command
    subparsers.add_parser("endpoints", help="List available API endpoints")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for opinions")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--page", type=int, default=1, help="Page number for pagination")
    search_parser.add_argument("--all", action="store_true", help="Retrieve all pages of results")
    search_parser.add_argument("--max-pages", type=int, default=10, help="Maximum number of pages to retrieve when using --all")
    search_parser.add_argument("--output", "-o", help="Save results to a JSON file")
    
    # Opinion command
    opinion_parser = subparsers.add_parser("opinion", help="Get details for a specific opinion")
    opinion_parser.add_argument("id", help="Opinion ID")
    opinion_parser.add_argument("--output", "-o", help="Save results to a JSON file")
    
    # Docket command
    docket_parser = subparsers.add_parser("docket", help="Get details for a specific docket")
    docket_parser.add_argument("id", help="Docket ID")
    docket_parser.add_argument("--output", "-o", help="Save results to a JSON file")
    
    # Citation command
    citation_parser = subparsers.add_parser("citation", help="Look up a case by citation")
    citation_parser.add_argument("citation", help="Citation to look up (e.g., \"410 U.S. 113\")")
    citation_parser.add_argument("--output", "-o", help="Save results to a JSON file")
    
    # Text command
    text_parser = subparsers.add_parser("text", help="Get the full text of an opinion by citation")
    text_parser.add_argument("citation", help="Citation to look up (e.g., \"410 U.S. 113\")")
    text_parser.add_argument("--metadata", action="store_true", help="Include opinion metadata")
    text_parser.add_argument("--output", "-o", help="Save text to a file")
    
    # Direct citation command
    direct_parser = subparsers.add_parser("direct", help="Get an opinion using direct citation format")
    direct_parser.add_argument("reporter", help="Reporter abbreviation (e.g., \"U.S.\")")
    direct_parser.add_argument("volume", help="Volume number")
    direct_parser.add_argument("page", help="Page number")
    direct_parser.add_argument("--output", "-o", help="Save results to a file")
    
    return parser.parse_args()

def save_to_file(data, filename):
    """Save data to a JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(data, indent=2, fp=f)
        print(f"Results saved to {filename}")
    except Exception as e:
        print(f"Error saving to file: {e}")

def main():
    """Command line interface for the CourtListener API client."""
    args = parse_args()
    
    if not args.command:
        print("Error: No command specified")
        return 1
    
    api = CourtListenerAPI(api_token)
    
    try:
        if args.command == "endpoints":
            endpoints = api.get_endpoints()
            for endpoint, url in endpoints.items():
                print(f"{endpoint}: {url}")
        
        elif args.command == "search":
            if args.all:
                results = api.get_all_search_results(args.query, max_pages=args.max_pages)
                data = {"count": len(results), "results": results}
            else:
                data = api.search_opinions(args.query, page=args.page)
            
            if args.output:
                save_to_file(data, args.output)
            else:
                print(json.dumps(data, indent=2))
        
        elif args.command == "opinion":
            opinion = api.get_opinion(args.id)
            if args.output:
                save_to_file(opinion, args.output)
            else:
                print(json.dumps(opinion, indent=2))
        
        elif args.command == "docket":
            docket = api.get_docket(args.id)
            if args.output:
                save_to_file(docket, args.output)
            else:
                print(json.dumps(docket, indent=2))
        
        elif args.command == "citation":
            results = api.citation_lookup(args.citation)
            if args.output:
                save_to_file(results, args.output)
            else:
                print(json.dumps(results, indent=2))
        
        elif args.command == "text":
            metadata, text = api.get_opinion_text_by_citation(args.citation)
            
            if not metadata:
                print(f"No opinion found for citation: {args.citation}")
                return 1
                
            if not text:
                print(f"Found citation but no text available for: {args.citation}")
                if metadata:
                    print(f"Case name: {metadata.get('caseName')}")
                    print(f"Court: {metadata.get('court')}")
                    print(f"Filed: {metadata.get('dateFiled')}")
                return 1
            
            if args.metadata:
                header = f"Case: {metadata.get('caseName')}\n"
                header += f"Citation: {args.citation}\n"
                header += f"Court: {metadata.get('court')}\n"
                header += f"Filed: {metadata.get('dateFiled')}\n"
                header += f"URL: https://www.courtlistener.com{metadata.get('absolute_url')}\n"
                header += "-" * 80 + "\n\n"
                output = header + text
            else:
                output = text
            
            if args.output:
                try:
                    with open(args.output, "w") as f:
                        f.write(output)
                    print(f"Opinion text saved to {args.output}")
                except Exception as e:
                    print(f"Error saving to file: {e}")
                    return 1
            else:
                print(output)
        
        elif args.command == "direct":
            opinion = api.get_opinion_by_url(args.reporter, args.volume, args.page)
            if args.output:
                save_to_file(opinion, args.output)
            else:
                print(json.dumps(opinion, indent=2))
        
        else:
            print(f"Unknown command: {args.command}")
    
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        print(f"API Error: {error_msg}")
        
        # Check for authentication errors
        if "401" in error_msg and "Unauthorized" in error_msg:
            print("\nAuthentication Error: This API endpoint requires authentication.")
            print("Please set your API token in the COURTLISTENER_API_TOKEN environment variable:")
            print("export COURTLISTENER_API_TOKEN=your_token_here")
            print("\nTo get an API token, register at https://www.courtlistener.com/ and")
            print("go to https://www.courtlistener.com/profile/api/")
        
        return 1
    
    return 0

# Make the module easily importable
__all__ = ['CourtListenerAPI']

if __name__ == "__main__":
    sys.exit(main()) 