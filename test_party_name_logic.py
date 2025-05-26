#!./.venv/bin/python
from eyecite import get_citations, clean_text
from eyecite.tokenizers import default_tokenizer
from eyecite.models import StopWordToken, CitationToken

def debug_citation_extraction(citation_text):
    """Debug the citation extraction logic for our citation"""
    print(f"Analyzing: {citation_text}")
    
    # Clean text
    cleaned_text = clean_text(citation_text, ["html"])
    print(f"Cleaned text: {cleaned_text}")
    
    # Manually tokenize
    words, citation_tokens = default_tokenizer.tokenize(cleaned_text)
    
    # Print all tokens to inspect
    print("\nTokens:")
    for i, token in enumerate(words):
        token_type = type(token).__name__
        if isinstance(token, StopWordToken):
            token_info = f"(stop_word: {token.groups['stop_word']})"
        elif isinstance(token, CitationToken):
            token_info = f"(citation: {token.groups})"
        else:
            token_info = ""
        print(f"  {i}: '{token}' {token_type} {token_info}")
    
    # Print citation tokens
    print("\nCitation Tokens:")
    for i, (token_index, token) in enumerate(citation_tokens):
        print(f"  Citation {i+1}: Index={token_index}, Token='{token}', Groups={token.groups}")
    
    # Get actual citation as eyecite would process it
    citations = get_citations(cleaned_text)
    if not citations:
        print("\nNo citations found!")
        return
    
    citation = citations[0]
    print(f"\nExtracted Citation: {citation}")
    print(f"Plaintiff: {citation.metadata.plaintiff}")
    print(f"Defendant: {citation.metadata.defendant}")
    print(f"Full span: {citation.full_span()}")
    print(f"Full span text: '{cleaned_text[citation.full_span()[0]:citation.full_span()[1]]}'")
    
    # Extract v token info
    v_token = None
    v_token_index = None
    for i, token in enumerate(words):
        if isinstance(token, StopWordToken) and token.groups.get("stop_word") == "v":
            v_token = token
            v_token_index = i
            break
    
    if v_token is None:
        print("\nNo 'v' token found")
    else:
        print(f"\n'v' token found at index {v_token_index}")
        print(f"Tokens preceding 'v': {[str(t) for t in words[max(v_token_index-2, 0):v_token_index]]}")
        
        # The algorithm only takes the last token (Dist.) as the plaintiff
        plaintiff_tokens = words[max(v_token_index-2, 0):v_token_index]
        print(f"Combined plaintiff tokens: {''.join(str(t) for t in plaintiff_tokens).strip()}")
        
    # Show why we're getting "Dist." as the plaintiff
    print("\nKey issue with the extraction:")
    print("1. The tokenizer correctly identifies 'v.' as a stop word")
    print("2. The add_defendant function in eyecite.helpers.py ONLY LOOKS AT THE LAST 2 TOKENS before 'v'")
    print("   instead of the entire case name with multiple parts")
    print("3. Code at line 150-151 in helpers.py extracts plaintiff: ")
    print("   citation.metadata.plaintiff = ''.join(str(w) for w in words[max(index - 2, 0) : index])")
    print("4. This only captures 'Dist.' instead of the full 'Austin Indep. Sch. Dist.'")

# Test on our problematic citation
debug_citation_extraction("Austin Indep. Sch. Dist. v. Sierra Club, 495 S.W.2d 878 (Tex. 1973)")