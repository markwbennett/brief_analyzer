#!./.venv/bin/python

from eyecite import get_citations

def test_citation():
    # Sample citation text
    citation_text = "Ball v. United States, 163 U.S. 662 (1896)\t24, 29"
    
    # Get citations using eyecite
    citations = get_citations(citation_text)
    
    # Create output file
    with open('eyecite_fields_output.txt', 'w') as f:
        for citation in citations:
            # Write all direct attributes of citation object
            for attr in dir(citation):
                if not attr.startswith('_') and not callable(getattr(citation, attr)):
                    value = getattr(citation, attr)
                    f.write(f"{attr}: {value}\n")
            
            # Write all groups
            f.write("\n# Groups:\n")
            for key, value in citation.groups.items():
                f.write(f"groups[{key}]: {value}\n")
            
            # Write all metadata attributes
            if citation.metadata:
                f.write("\n# Metadata:\n")
                for attr in dir(citation.metadata):
                    if not attr.startswith('_') and not callable(getattr(citation.metadata, attr)):
                        value = getattr(citation.metadata, attr)
                        f.write(f"metadata.{attr}: {value}\n")
    
    print(f"Citation fields written to eyecite_fields_output.txt")

if __name__ == "__main__":
    test_citation() 