#!/!/./.venv/bin/python
"""
Get Opinion Text

A simple script to get the full text of an opinion from CourtListener by citation.
"""

import os
import sys
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API token from environment
api_token = os.getenv('COURT_LISTENER_TOKEN')
if not api_token:
    print("Error: COURT_LISTENER_TOKEN not found in .env file")
    sys.exit(1)

# Basic authentication with token for downloading case text
headers = {'Authorization': f'Token {api_token}'}

def get_opinion_by_id(opinion_id):
    """Fetch an opinion by its ID"""
    url = f'https://www.courtlistener.com/api/rest/v3/opinions/{opinion_id}/'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_opinions_by_citation(citation):
    """Fetch opinions matching a citation"""
    url = f'https://www.courtlistener.com/api/rest/v3/opinions/?cluster__citation={citation}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_direct_opinion(reporter, volume, page):
    """Get an opinion using the direct citation URL format."""
    base_url = "https://www.courtlistener.com"
    url = f"{base_url}/c/{reporter}/{volume}/{page}/"
    
    print(f"Trying direct URL: {url}")
    
    try:
        # Make a GET request to the URL
        response = requests.get(url, allow_redirects=True)
        response.raise_for_status()
        
        print(f"Redirected to: {response.url}")
        
        # If we got redirected to an opinion page, extract the ID
        if "/opinion/" in response.url:
            # Extract opinion ID from URL
            parts = response.url.split("/")
            for i, part in enumerate(parts):
                if part == "opinion" and i+1 < len(parts):
                    opinion_id = parts[i+1]
                    print(f"Found opinion ID: {opinion_id}")
                    
                    # Get the case name
                    case_name = None
                    if len(parts) > i+2:
                        case_name_slug = parts[i+2]
                        case_name = case_name_slug.replace('-', ' ').title()
                        print(f"Case name: {case_name}")
                    
                    return {
                        "id": opinion_id,
                        "url": response.url,
                        "case_name": case_name,
                        "citation": f"{volume} {reporter} {page}"
                    }
    except Exception as e:
        print(f"Error: {e}")
    
    return None

def get_api_opinion(citation):
    """Get an opinion using the API citation lookup."""
    base_url = "https://www.courtlistener.com/api/rest/v4"
    url = f"{base_url}/citation-lookup/?citation={citation}"
    
    print(f"Trying API URL: {url}")
    
    try:
        # Make a GET request to the API
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Parse the JSON response
        data = response.json()
        if data and len(data) > 0:
            match = data[0]
            print(f"Found match: {match.get('caseName')}")
            
            # Get the opinion ID
            opinion_id = match.get('id')
            if opinion_id:
                # Get the full opinion data
                opinion_url = f"{base_url}/opinions/{opinion_id}/"
                opinion_response = requests.get(opinion_url, headers=headers)
                opinion_response.raise_for_status()
                
                opinion_data = opinion_response.json()
                return {
                    "id": opinion_id,
                    "url": f"https://www.courtlistener.com{match.get('absolute_url')}",
                    "case_name": match.get('caseName'),
                    "citation": citation,
                    "text": opinion_data.get('plain_text')
                }
    except Exception as e:
        print(f"API Error: {e}")
    
    return None

def get_simple_opinion_text(citation=None, reporter=None, volume=None, page=None):
    """Get the text of an opinion by citation or direct reference."""
    result = None
    
    # Try direct citation first if components are provided
    if reporter and volume and page:
        result = get_direct_opinion(reporter, volume, page)
    
    # If direct citation failed or wasn't provided, try API
    if not result and citation:
        result = get_api_opinion(citation)
    
    return result

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Get by ID:       python get_opinion_text.py --id OPINION_ID")
        print("  Get by citation: python get_opinion_text.py --citation 'CITATION'")
        sys.exit(1)
    
    try:
        if sys.argv[1] == "--id" and len(sys.argv) >= 3:
            opinion_id = sys.argv[2]
            result = get_opinion_by_id(opinion_id)
            print(f"Case: {result.get('case_name', 'Unknown')}")
            if 'plain_text' in result:
                print("\nOPINION TEXT:")
                print(result['plain_text'])
            else:
                print("No plain text available in the response")
        
        elif sys.argv[1] == "--citation" and len(sys.argv) >= 3:
            citation = sys.argv[2]
            results = get_opinions_by_citation(citation)
            count = results.get('count', 0)
            print(f"Found {count} opinions matching citation: {citation}")
            
            if count > 0:
                for i, opinion in enumerate(results.get('results', [])):
                    print(f"\nResult {i+1}: {opinion.get('case_name', 'Unknown')}")
                    opinion_id = opinion.get('id')
                    if opinion_id:
                        full_opinion = get_opinion_by_id(opinion_id)
                        if 'plain_text' in full_opinion:
                            print("\nOPINION TEXT:")
                            print(full_opinion['plain_text'])
                        else:
                            print("No plain text available in the response")
        else:
            print("Invalid arguments")
            print("Usage:")
            print("  Get by ID:       python get_opinion_text.py --id OPINION_ID")
            print("  Get by citation: python get_opinion_text.py --citation 'CITATION'")
    
    except requests.exceptions.HTTPError as e:
        print(f"API Error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sys.exit(main()) 