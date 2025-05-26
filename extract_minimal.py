#!./.venv/bin/python

from eyecite import get_citations

def extract_minimal_citation_data(text):
    citations = get_citations(text)
    results = []
    
    for citation in citations:
        # Extract only the needed fields
        volume = citation.groups.get('volume')
        reporter = citation.groups.get('reporter')
        page = citation.groups.get('page')
        
        if volume and reporter and page:
            results.append({
                'volume': volume,
                'reporter': reporter,
                'page': page
            })
    
    return results

if __name__ == "__main__":
    citation_text = "Ball v. United States, 163 U.S. 662 (1896)\t24, 29"
    minimal_data = extract_minimal_citation_data(citation_text)
    
    for i, citation in enumerate(minimal_data):
        print(f"Citation {i+1}:")
        print(f"  Volume: {citation['volume']}")
        print(f"  Reporter: {citation['reporter']}")
        print(f"  Page: {citation['page']}")
        print(f"  Full Citation: {citation['volume']} {citation['reporter']} {citation['page']}") 