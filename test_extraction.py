#!./.venv/bin/python
import argparse
import sys
from pathlib import Path

from eyecite import get_citations, clean_text

def extract_citations(text):
    """
    Extract citations from legal text using eyecite with detailed debugging
    """
    print(f"Original text: {text}")
    
    # Clean text more gently
    cleaned_text = clean_text(text, ["html"])
    print(f"Cleaned text: {cleaned_text}")
    
    # Get all citations from the text
    citations = get_citations(cleaned_text, full_context=True)
    print(f"Number of citations found: {len(citations)}")
    
    # Analyze each citation
    for i, citation in enumerate(citations):
        print(f"\nCitation {i+1}:")
        print(f"Type: {citation.__class__.__name__}")
        print(f"Full text: {citation}")
        
        # Print span information
        span = citation.span()
        print(f"Span: {span}")
        print(f"Matched text in span: '{cleaned_text[span[0]:span[1]]}'")
        
        full_span = citation.full_span()
        print(f"Full span: {full_span}")
        print(f"Full text in span: '{cleaned_text[full_span[0]:full_span[1]]}'")
        
        # Print metadata
        if hasattr(citation, "metadata") and citation.metadata:
            print("\nMetadata:")
            meta = citation.metadata
            for attr_name in dir(meta):
                if not attr_name.startswith('_') and not callable(getattr(meta, attr_name)):
                    value = getattr(meta, attr_name)
                    if value is not None:
                        print(f"  {attr_name}: {value}")
        
        # Print groups
        if hasattr(citation, "groups") and citation.groups:
            print("\nGroups:")
            for key, value in citation.groups.items():
                print(f"  {key}: {value}")

def main():
    parser = argparse.ArgumentParser(description='Test eyecite citation extraction with detailed output')
    
    # Add argument for citation text
    parser.add_argument('--text', type=str, help='Citation text to analyze')
    
    # Add argument for file containing citation
    parser.add_argument('--file', type=str, help='File containing citation text')
    
    args = parser.parse_args()
    
    # Get text either from argument or file
    if args.text:
        text = args.text
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file: {str(e)}")
            sys.exit(1)
    else:
        # Default test citation
        text = "Austin Indep. Sch. Dist. v. Sierra Club, 495 S.W.2d 878 (Tex. 1973)"
    
    # Extract and analyze citations
    extract_citations(text)

if __name__ == "__main__":
    main()