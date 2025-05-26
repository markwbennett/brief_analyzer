#!/./.venv/bin/python

import os
import json
import requests
import re
from datetime import datetime

def get_citation_input():
    citation = input("Enter citation (in the form volume reporter page, e.g. '347 U.S. 483'): ")
    parts = citation.strip().split(' ', 2)
    
    if len(parts) < 3:
        print("Invalid citation format. Please use 'volume reporter page' format.")
        return get_citation_input()
    
    volume = parts[0]
    page = parts[-1]
    reporter = ' '.join(parts[1:-1])
    
    print(f"Parsed as - Volume: {volume}, Reporter: {reporter}, Page: {page}")
    confirm = input("Is this correct? (y/n): ").lower()
    
    if confirm != 'y':
        return get_citation_input()
    
    return volume, reporter, page

def lookup_citation(volume, reporter, page):
    api_url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
    token = "b6bc45c46b6507dcde53992ef3523e46e5a9e3ed"
    
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "volume": volume,
        "reporter": reporter,
        "page": page
    }
    
    response = requests.post(api_url, headers=headers, data=data)
    return response

def save_to_file(response, volume, reporter, page):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"citation_{volume}_{reporter}_{page}_{timestamp}.txt"
    
    with open(filename, "w") as f:
        if response.status_code == 200:
            f.write(json.dumps(response.json(), indent=2))
        else:
            f.write(f"Error: {response.status_code}\n")
            f.write(response.text)
    
    return filename

def main():
    print("Citation Lookup Tool")
    print("-------------------")
    
    volume, reporter, page = get_citation_input()
    print(f"\nLooking up citation: {volume} {reporter} {page}")
    
    response = lookup_citation(volume, reporter, page)
    filename = save_to_file(response, volume, reporter, page)
    
    print(f"\nResponse saved to {filename}")
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 200:
        print("Citation found successfully!")
    else:
        print(f"Error retrieving citation: {response.text}")

if __name__ == "__main__":
    main() 