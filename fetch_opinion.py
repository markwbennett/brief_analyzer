#!/usr/bin/env python
import os
import sys
import requests
import re
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

# Request timeout (in seconds)
TIMEOUT = 30

def parse_citation(citation):
    """Parse a citation into volume, reporter, and page"""
    # Common pattern: [volume] [reporter] [page]
    # Examples: "347 U.S. 483", "410 U.S. 113", "698 S.W.2d 362"
    match = re.match(r'(\d+?) (.+?) (\d+?)$', citation)
    if match:
        volume, reporter, page = match.groups()
        return volume, reporter, page
    return None, None, None

def get_opinion_by_citation(volume, reporter, page):
    """Look up a case by volume, reporter, and page"""
    print(f"Looking up citation: {volume} {reporter} {page}")
    
    # Use only the POST-based citation lookup method
    opinion_id = post_citation_lookup(volume, reporter, page)
    if opinion_id:
        return get_opinion_by_id(opinion_id)
    
    print(f"No opinion found for citation: {volume} {reporter} {page}")
    return None

def post_citation_lookup(volume, reporter, page):
    """Look up a case citation using the POST method"""
    print("Looking up citation via POST request...")
    
    api_url = "https://www.courtlistener.com/api/rest/v3/citation-lookup/"
    
    # Set up headers with content type for form submission
    post_headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # Form data for the POST request
    data = {
        "volume": volume,
        "reporter": reporter,
        "page": page
    }
    
    try:
        print(f"POST request with data: {data}")
        response = requests.post(api_url, headers=post_headers, data=data, timeout=TIMEOUT)
        response.raise_for_status()
        result = response.json()
        
        # Save POST response to file for debugging
        debug_filename = f"citation_lookup_post_{volume}_{reporter}_{page}.json"
        with open(debug_filename, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Saved POST response to {debug_filename}")
        
        # Extract the ID from the clusters array
        if result and isinstance(result, list) and len(result) > 0:
            if 'clusters' in result[0] and result[0]['clusters'] and len(result[0]['clusters']) > 0:
                opinion_id = result[0]['clusters'][0]['id']
                print(f"Found opinion ID from clusters: {opinion_id}")
                return opinion_id
            else:
                print("No clusters found in the response")
        else:
            print("Empty or invalid response")
        
        return None
    
    except Exception as e:
        print(f"Citation lookup failed: {e}")
        return None

def get_opinion_by_id(opinion_id):
    """Fetch the full opinion by ID"""
    print(f"Fetching opinion with ID: {opinion_id}")
    url = f'https://www.courtlistener.com/api/rest/v3/opinions/{opinion_id}/'
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        # Save opinion data to file for debugging
        debug_filename = f"opinion_data_{opinion_id}.json"
        with open(debug_filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved opinion data to {debug_filename} for debugging")
        
        return data
    except requests.exceptions.Timeout:
        print(f"Request timed out after {TIMEOUT} seconds.")
        return None
    except Exception as e:
        print(f"Error retrieving opinion: {e}")
        return None

def main():
    # Prompt user for citation or ID
    user_input = input("Enter legal citation (e.g., '347 U.S. 483') or opinion ID: ").strip()
    if not user_input:
        print("Error: No input provided")
        return 1
    
    # Check if input is just a numeric ID
    if user_input.isdigit():
        print(f"Treating input as opinion ID: {user_input}")
        opinion = get_opinion_by_id(user_input)
        if not opinion:
            print(f"No opinion found with ID: {user_input}")
            return 1
    else:
        # Parse the citation
        volume, reporter, page = parse_citation(user_input)
        if not all([volume, reporter, page]):
            print("Error: Could not parse citation. Please use format like '347 U.S. 483'")
            
            # Ask if they want to search by case name instead
            search_name = input("Would you like to search by case name instead? (y/n): ").strip().lower()
            if search_name == 'y':
                case_name = input("Enter case name to search: ").strip()
                if case_name:
                    opinion = search_by_case_name(case_name)
                    if not opinion:
                        print(f"No opinion found for case name: {case_name}")
                        return 1
                else:
                    print("No case name provided")
                    return 1
            else:
                return 1
        else:
            # Get the opinion by citation
            opinion = get_opinion_by_citation(volume, reporter, page)
            
            if not opinion:
                print(f"No opinion found for citation: {volume} {reporter} {page}")
                return 1
    
    # Display opinion information
    case_name = opinion.get('case_name', 'Unknown case')
    court = opinion.get('court_name', 'Unknown court')
    
    print(f"\nCASE: {case_name}")
    print(f"COURT: {court}")
    if 'date_filed' in opinion:
        print(f"FILED: {opinion['date_filed']}")
    
    # Check if text is available
    if 'plain_text' in opinion and opinion['plain_text']:
        text = opinion['plain_text']
        
        # Show a preview
        preview_lines = text.split('\n')[:20]
        preview = '\n'.join(preview_lines)
        print("\n" + "-" * 80)
        print(preview)
        if len(preview_lines) < text.count('\n'):
            print("...(text continues)...")
        print("-" * 80)
        
        # Ask if user wants to see full text
        show_full = input("\nShow full text? (y/n): ").strip().lower()
        if show_full == 'y':
            print("\n" + "-" * 80)
            print(text)
            print("-" * 80)
        
        # Offer to save to file
        save = input("\nSave to file? (y/n): ").strip().lower()
        if save == 'y':
            # Save the raw opinion data to JSON
            opinion_id = opinion.get('id', 'unknown')
            json_filename = f"opinion_data_{opinion_id}.json"
            
            with open(json_filename, 'w') as f:
                json.dump(opinion, f, indent=2)
            print(f"Saved opinion data to {json_filename}")
            
            # Ask if they want to format the opinion
            format_opinion = input("\nFormat the opinion in multiple formats (HTML, PDF, etc.)? (y/n): ").strip().lower()
            if format_opinion == 'y':
                import subprocess
                
                # Determine the citation to use for the filename
                original_citation = user_input
                if not user_input.isdigit():  # It's a citation, not an ID
                    citation_arg = f"--citation \"{original_citation}\""
                else:
                    citation_arg = ""
                
                cmd = f"python format_opinion.py {json_filename} {citation_arg}"
                try:
                    subprocess.run(cmd, shell=True, check=True)
                    print("Opinion formatted successfully")
                except subprocess.CalledProcessError as e:
                    print(f"Error formatting opinion: {e}")
            else:
                # Just save the text to a file
                if not user_input.isdigit():  # It's a citation
                    clean_citation = user_input.replace(' ', '_').replace('.', '')
                    filename = f"citation_{clean_citation}.txt"
                else:
                    filename = f"opinion_{opinion_id}.txt"
                
                with open(filename, 'w') as f:
                    f.write(text)
                print(f"Saved text to {filename}")
    else:
        print("No plain text available for this opinion")
    
    return 0

def search_by_case_name(case_name):
    """Search for an opinion by case name"""
    print(f"Searching for case: {case_name}")
    url = f"https://www.courtlistener.com/api/rest/v3/search/?type=o&q={case_name}"
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        # Save case name search results to file for debugging
        debug_filename = f"case_search_{case_name.replace(' ', '_')}.json"
        with open(debug_filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved case search results to {debug_filename} for debugging")
        
        if data.get('count', 0) > 0 and 'results' in data:
            # Show the top 5 results and let user choose
            print(f"Found {data['count']} results. Top matches:")
            
            for i, result in enumerate(data['results'][:5]):
                print(f"[{i+1}] {result.get('caseName', 'Unknown')} ({result.get('court_citation_string', 'Unknown citation')})")
            
            choice = input("Enter number to select (or 0 to cancel): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= min(5, len(data['results'])):
                result = data['results'][int(choice)-1]
                opinion_id = result.get('id')
                if opinion_id:
                    return get_opinion_by_id(opinion_id)
    except Exception as e:
        print(f"Case name search failed: {e}")
    
    return None

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 