#!./.venv/bin/python
from eyecite import get_citations, clean_text

# Test citation
text = "Austin Indep. Sch. Dist. v. Sierra Club, 495 S.W.2d 878 (Tex. 1973)"

# Clean text
cleaned_text = clean_text(text, ["html"])

# Get citations
citations = get_citations(cleaned_text)

# Print results
print(f"Number of citations found: {len(citations)}")
print("\nCitation details:")
for i, citation in enumerate(citations):
    print(f"\nCitation {i+1}:")
    print(f"Type: {citation.__class__.__name__}")
    print(f"Full text: {str(citation)}")
    
    # Print all available attributes
    print("\nAttributes:")
    for attr in dir(citation):
        if not attr.startswith("_") and attr not in ["metadata", "match"]:
            try:
                value = getattr(citation, attr)
                if not callable(value):
                    print(f"  {attr}: {value}")
            except:
                pass
    
    # Print metadata if available
    if hasattr(citation, "metadata") and citation.metadata:
        print("\nMetadata:")
        for attr in dir(citation.metadata):
            if not attr.startswith("_"):
                try:
                    value = getattr(citation.metadata, attr)
                    if not callable(value):
                        print(f"  {attr}: {value}")
                except:
                    pass