#!./.venv/bin/python
from eyecite import get_citations, clean_text
from eyecite.helpers import match_on_tokens, add_defendant
from eyecite.regexes import PRE_FULL_CITATION_REGEX

def test_citation(text):
    """Test how the eyecite library handles a specific citation"""
    print(f"Testing citation: {text}")
    
    # Clean text
    cleaned_text = clean_text(text, ["html"])
    
    # Get citations
    citations = get_citations(cleaned_text)
    
    # Print results
    print(f"\nNumber of citations found: {len(citations)}")
    for i, citation in enumerate(citations):
        print(f"\nCitation {i+1}:")
        print(f"Type: {citation.__class__.__name__}")
        print(f"Full text: {str(citation)}")
        
        # Print metadata
        if hasattr(citation, "metadata") and citation.metadata:
            meta = citation.metadata
            print("\nMetadata:")
            if hasattr(meta, "plaintiff"):
                print(f"  Plaintiff: {meta.plaintiff if meta.plaintiff else 'None'}")
            if hasattr(meta, "defendant"):
                print(f"  Defendant: {meta.defendant if meta.defendant else 'None'}")
            if hasattr(meta, "court"):
                print(f"  Court: {meta.court if meta.court else 'None'}")
            if hasattr(meta, "year"):
                print(f"  Year: {meta.year if meta.year else 'None'}")
        
        if hasattr(citation, "full_span"):
            span = citation.full_span()
            print(f"\nFull span: {span}")
            print(f"Text in full span: {cleaned_text[span[0]:span[1]]}")

# Test with various formats of the citation
citations_to_test = [
    "Austin Indep. Sch. Dist. v. Sierra Club, 495 S.W.2d 878 (Tex. 1973)",
    "Austin Independent School District v. Sierra Club, 495 S.W.2d 878 (Tex. 1973)",
    "A.I.S.D. v. Sierra Club, 495 S.W.2d 878 (Tex. 1973)"
]

for citation in citations_to_test:
    test_citation(citation)
    print("\n" + "-"*70 + "\n")