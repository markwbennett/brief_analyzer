#!./.venv/bin/python
import argparse
import json
import sys
import os
import re
from pathlib import Path
import io
import html
import copy
from collections import defaultdict

from eyecite import get_citations, clean_text
from eyecite.resolve import resolve_citations
from eyecite.tokenizers import HyperscanTokenizer

# For PDF extraction
from pdfminer.high_level import extract_text as pdf_extract_text

# For DOCX extraction
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("Warning: python-docx not found. DOCX support disabled.")

# Import our legal abbreviations expander
try:
    from legal_abbreviations import expand_abbreviations
    ABBREVIATIONS_AVAILABLE = True
except ImportError:
    ABBREVIATIONS_AVAILABLE = False
    print("Warning: legal_abbreviations.py not found. Abbreviation expansion disabled.")

def normalize_whitespace(text):
    """Normalize whitespace while preserving important line breaks."""
    # First replace multiple spaces with a single space
    text = re.sub(r' {2,}', ' ', text)
    # Replace multiple newlines with a double newline to preserve paragraph breaks
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file with improved whitespace handling."""
    try:
        text = pdf_extract_text(pdf_path)
        # Normalize whitespace while preserving important line breaks
        text = normalize_whitespace(text)
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return ""

def extract_text_from_docx(docx_path):
    """Extract text from a DOCX file."""
    if not DOCX_AVAILABLE:
        print("Error: python-docx module not available. Please install it with 'pip install python-docx'")
        return ""
    
    try:
        doc = docx.Document(docx_path)
        text = []
        for para in doc.paragraphs:
            text.append(para.text)
        
        # Join paragraphs with newlines
        full_text = '\n'.join(text)
        # Normalize whitespace
        full_text = normalize_whitespace(full_text)
        return full_text
    except Exception as e:
        print(f"Error extracting text from DOCX: {str(e)}")
        return ""

def extract_table_of_authorities(text):
    """Extract case names and citations from the Table of Authorities section."""
    case_data = {}
    
    # Look for Table of Authorities section
    toa_match = re.search(r'(?i)Table\s+of\s+Authorities.*?\n+Cases\s*\n+(.*?)(?:\n+Statutes|\n+Constitutional|\n+Treatises|\n+Other|\Z)', text, re.DOTALL)
    if not toa_match:
        # Try a more flexible approach if the above pattern doesn't work
        toa_match = re.search(r'(?i)Table\s+of\s+Authorities(.*?)(?:\n\n\s*[A-Za-z]+|\Z)', text, re.DOTALL)
        if not toa_match:
            return case_data
    
    # Extract the cases section
    toa_text = toa_match.group(1)
    
    # Look for the 'Cases' subsection if it wasn't already captured
    if 'Cases' not in toa_text[:50]:
        cases_match = re.search(r'(?i)(?:^|\n)Cases(.*?)(?:\n\n\s*[A-Za-z]+|\Z)', toa_text, re.DOTALL)
        if cases_match:
            cases_text = cases_match.group(1)
        else:
            cases_text = toa_text
    else:
        cases_text = toa_text
    
    # Process the cases text with a more robust approach
    # Split by newlines but try to join case entries that span multiple lines
    lines = cases_text.split('\n')
    processed_lines = []
    current_line = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # If line starts with a case name or continues a citation, add to current line
        if re.match(r'^[A-Za-z]', line) or re.search(r'\d+\s*$', current_line):
            if current_line:
                current_line += " " + line
            else:
                current_line = line
        # If line contains page numbers at the end, it's likely the end of a citation
        elif re.search(r'\d+(?:,\s*\d+)*\s*$', line) and current_line:
            current_line += " " + line
            processed_lines.append(current_line)
            current_line = ""
        else:
            if current_line:
                processed_lines.append(current_line)
            current_line = line
    
    if current_line:
        processed_lines.append(current_line)
    
    # Process each entry to extract case information
    for entry in processed_lines:
        # Match case name and citation - handling a variety of formats
        citation_match = re.search(r'(.*?),\s+((?:\d+\s+(?:[A-Za-z0-9.]+)\s+\d+).*?\((?:\w+\.?(?:\s+\w+\.?)*\s+\d{4}|Tex\.\s+App\..*?)\))', entry)
        if citation_match:
            case_title = citation_match.group(1).strip()
            citation_text = citation_match.group(2).strip()
            
            # Handle special case for unpublished cases with WL citations
            wl_match = re.search(r'No\.\s+[\w\-]+,\s+(\d{4})\s+WL\s+(\d+)', citation_text)
            if wl_match:
                # This is a WL citation
                year = wl_match.group(1)
                number = wl_match.group(2)
                key = f"{year} WL {number}"
                
                case_data[key] = {
                    "title": case_title,
                    "citation": citation_text,
                    "is_unpublished": True,
                    "wl_cite": key
                }
                
                # Extract cause number if present
                cause_match = re.search(r'No\.\s+([\w\-]+)', citation_text)
                if cause_match:
                    case_data[key]["case_number"] = cause_match.group(1)
                
                # Extract plaintiff and defendant
                name_parts = case_title.split(' v. ')
                if len(name_parts) == 2:
                    case_data[key]['plaintiff'] = name_parts[0].strip()
                    case_data[key]['defendant'] = name_parts[1].strip()
                
                continue
            
            # Regular case citation
            volume_reporter_page = re.search(r'(\d+)\s+([A-Za-z0-9.]+)\s+(\d+)', citation_text)
            if volume_reporter_page:
                volume = volume_reporter_page.group(1)
                reporter = volume_reporter_page.group(2)
                page = volume_reporter_page.group(3)
                
                # Create a citation key
                key = f"{volume} {reporter} {page}"
                
                # Extract year if present
                year_match = re.search(r'\((?:.*?)(\d{4})\)', citation_text)
                year = year_match.group(1) if year_match else None
                
                # Store the case information
                case_data[key] = {
                    "title": case_title,
                    "citation": citation_text,
                    "volume": volume,
                    "reporter": reporter,
                    "page": page
                }
                
                if year:
                    case_data[key]["year"] = year
                
                # Find pinpoint citations referenced in the document
                pin_cite_match = re.search(r'\)(?:.*?)(\d+(?:,\s*\d+)*)\s*$', entry)
                if pin_cite_match:
                    pin_cites = [p.strip() for p in pin_cite_match.group(1).split(',')]
                    case_data[key]["pin_cites"] = pin_cites
                
                # Extract plaintiff and defendant
                name_parts = case_title.split(' v. ')
                if len(name_parts) == 2:
                    case_data[key]['plaintiff'] = name_parts[0].strip()
                    case_data[key]['defendant'] = name_parts[1].strip()
    
    return case_data

def save_cleaned_text(text, original_file):
    """Save cleaned text to a file."""
    cleaned_path = f"{original_file.stem}_cleaned.txt"
    with open(cleaned_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return cleaned_path

def preprocess_text_for_citations(text):
    """
    Preprocess text to improve citation recognition by expanding legal abbreviations
    that might cause issues with eyecite parsing.
    """
    if ABBREVIATIONS_AVAILABLE:
        # Use our comprehensive list of legal abbreviations
        return expand_abbreviations(text)
    else:
        # Fallback to basic abbreviation handling if the module isn't available
        # Common abbreviated organization names that might cause parsing issues
        org_patterns = [
            (r"([A-Za-z\.]+)\s+Indep\.\s+Sch\.\s+Dist\.", r"\1 Independent School District"),
            (r"([A-Za-z\.]+)\s+Cnty\.", r"\1 County"),
            (r"([A-Za-z\.]+)\s+Dep't", r"\1 Department"),
            (r"([A-Za-z\.]+)\s+Ass'n", r"\1 Association"),
            (r"([A-Za-z\.]+)\s+Auth\.", r"\1 Authority"),
            (r"([A-Za-z\.]+)\s+Comm'n", r"\1 Commission"),
        ]
        
        # Apply normalization patterns to the text
        preprocessed_text = text
        for pattern, replacement in org_patterns:
            preprocessed_text = re.sub(pattern, replacement, preprocessed_text)
            
        return preprocessed_text

def extract_case_title_from_context(context, citation_index):
    """Extract case title from text preceding a citation."""
    # If the citation is at the beginning of the context, we can't extract a title
    if citation_index <= 5:
        return None
    
    # Get text before the citation
    prefix = context[:citation_index].strip()
    
    # Look for common patterns in case titles
    # Pattern: Text ending with v.
    v_match = re.search(r'([A-Za-z0-9\s\.,&;\'"\-]+\sv\.\s[A-Za-z0-9\s\.,&;\'"\-]+)(?:,|\s+$)', prefix)
    if v_match:
        return v_match.group(1).strip()
    
    # Pattern: Last comma-separated segment (often the case name)
    comma_segments = prefix.split(',')
    if len(comma_segments) > 1:
        # Get the text after the last comma
        potential_title = comma_segments[-1].strip()
        # Check if it looks like a case title (has 'v.' in it)
        if ' v. ' in potential_title:
            return potential_title
    
    # If we can't find a clear pattern, return the last sentence
    sentences = re.split(r'[.?!]\s+', prefix)
    if sentences:
        last_sentence = sentences[-1].strip()
        # Only return if it might be a case title
        if ' v. ' in last_sentence:
            return last_sentence
    
    return None

def create_google_scholar_url(citation):
    """Create a Google Scholar URL for a citation."""
    
    # Handle unpublished cases with WL citation
    if citation.get("is_unpublished") and citation.get("wl_cite"):
        return f"https://scholar.google.com/scholar?q=+{citation.get('wl_cite')}&hl=en&as_sdt=2&btnI=1"
    
    # Handle unpublished cases with case number
    if citation.get("is_unpublished") and citation.get("case_number"):
        return f"https://scholar.google.com/scholar?q=+{citation.get('case_number')}&hl=en&as_sdt=2&btnI=1"
    
    # Standard case citation
    volume = citation.get("volume", "")
    reporter = citation.get("reporter", "")
    page = citation.get("page", "")
    
    # Clean up any spaces in the components
    volume = str(volume).strip()
    reporter = str(reporter).strip()
    page = str(page).strip()
    
    if volume and reporter and page:
        return f"https://scholar.google.com/scholar?q={volume}+{reporter}+{page}&hl=en&as_sdt=2&btnI=1"
    
    # Fallback: if we have a complete case title
    if citation.get("plaintiff") and citation.get("defendant"):
        plaintiff = citation.get("plaintiff", "").strip()
        defendant = citation.get("defendant", "").strip()
        return f"https://scholar.google.com/scholar?q={plaintiff}+v.+{defendant}&hl=en&as_sdt=2&btnI=1"
    
    return None

def create_court_url(citation):
    """Create a court website URL for certain citation types."""
    # Texas court website URL for case numbers
    if citation.get("is_unpublished") and citation.get("case_number"):
        cause_number = citation.get("case_number")
        
        # Check if the cause number already has -CR or -CV suffix
        if not (cause_number.endswith("-CR") or cause_number.endswith("-CV")):
            # Default to criminal case (-CR)
            cause_number = f"{cause_number}-CR"
        
        return f"https://search.txcourts.gov/Case.aspx?cn={cause_number}"
    
    return None

def detect_unpublished_case(text, index, length):
    """
    Detect if a section of text contains an unpublished case with a cause number
    in the format \n\n-\n\n-\n\n\n\n\n-C[R|V] or WL citation.
    """
    # Limit the context to search
    context_start = max(0, index - 400)
    context_end = min(len(text), index + length + 400)
    context = text[context_start:context_end]
    
    # Try to find cause number pattern for unpublished cases in Texas
    # Pattern like -XX-XX-XXXXX-CR or -XX-XX-XXXXX-CV
    cause_number_pattern = r'(?:^|\s)(\d{2}-\d{2}-\d{5}-(?:CR|CV)|No\.\s+\d{2}-\d{2}-\d{5}-(?:CR|CV))'
    cause_match = re.search(cause_number_pattern, context, re.IGNORECASE)
    
    # WL citation pattern
    wl_standard_pattern = r'(\d{4})\s+WL\s+(\d+)'
    wl_match = re.search(wl_standard_pattern, context)
    
    # Extract case title from context
    citation_position = index - context_start
    case_title = extract_case_title_from_context(context, citation_position)
    
    result = {
        "is_unpublished": False,
        "case_title": case_title,
        "text": context
    }
    
    # Check for a WL citation first
    if wl_match:
        year = wl_match.group(1)
        number = wl_match.group(2)
        wl_cite = f"{year} WL {number}"
        
        result["is_unpublished"] = True
        result["reporter"] = "WL"
        result["volume"] = year
        result["page"] = number
        result["wl_cite"] = wl_cite
        result["case_title"] = case_title
        result["google_scholar_url"] = f"https://scholar.google.com/scholar?q=+{wl_cite}&hl=en&as_sdt=2&btnI=1"
        
        # If we still don't have a case title, try to extract from context
        if not case_title:
            # Look for pattern: text ending with comma before "No."
            if "No." in context:
                no_pos = context.find("No.")
                prefix = context[:no_pos].strip()
                # Find the last comma before "No."
                comma_pos = prefix.rfind(',')
                if comma_pos > 0:
                    title_candidate = prefix[comma_pos+1:].strip()
                    # Check if it might be a valid title segment
                    if len(title_candidate) > 5 and not re.match(r'^\d', title_candidate):
                        result["case_title"] = title_candidate
        
        # Try to find a cause number too for court URL
        if cause_match:
            cause_number = cause_match.group(1).strip()
            # Clean up "No. " prefix if present
            if cause_number.startswith("No."):
                cause_number = cause_number[3:].strip()
                
            result["case_number"] = cause_number
            court_case_number = cause_number
            if not (cause_number.endswith("-CR") or cause_number.endswith("-CV")):
                court_case_number = f"{cause_number}-CR"  # Default to criminal
            result["court_url"] = f"https://search.txcourts.gov/Case.aspx?cn={court_case_number}"
        
        return result
    
    # Next check for cause number pattern
    elif cause_match:
        cause_number = cause_match.group(1).strip()
        # Clean up "No. " prefix if present
        if cause_number.startswith("No."):
            cause_number = cause_number[3:].strip()
            
        result["is_unpublished"] = True
        result["case_number"] = cause_number
        result["google_scholar_url"] = f"https://scholar.google.com/scholar?q=+{cause_number}&hl=en&as_sdt=2&btnI=1"
        
        # Generate the court URL
        court_case_number = cause_number
        if not (cause_number.endswith("-CR") or cause_number.endswith("-CV")):
            court_case_number = f"{cause_number}-CR"  # Default to criminal
        result["court_url"] = f"https://search.txcourts.gov/Case.aspx?cn={court_case_number}"
        
        return result
    
    return result

def extract_case_citations(text, find_pinpoint_cites=False, known_case_titles=None):
    """
    Extract case citations from legal text with enhanced unpublished case detection.
    """
    if known_case_titles is None:
        known_case_titles = {}
    
    # Clean text gently to preserve context
    cleaned_text = clean_text(text, ["html"])
    
    # Preprocess text to handle abbreviated organization names
    preprocessed_text = preprocess_text_for_citations(cleaned_text)
    
    # Get citations using eyecite
    raw_citations = get_citations(preprocessed_text)
    
    # Process citations to a more structured format
    structured_citations = []
    seen_citations = set()  # Track unique citation strings to avoid duplicates
    
    # First process full citations
    for citation in raw_citations:
        # Skip duplicate citations
        citation_text = str(citation)
        if citation_text in seen_citations:
            continue
        seen_citations.add(citation_text)
        
        # Skip section symbol citations
        if citation.__class__.__name__ == "UnknownCitation" and "§" in citation_text:
            continue
        
        # Basic citation info
        citation_info = {
            "type": citation.__class__.__name__,
            "text": citation_text
        }
        
        # Add span information if available
        if hasattr(citation, 'span_start') and citation.span_start is not None and \
           hasattr(citation, 'span_end') and citation.span_end is not None:
            citation_info["span"] = [citation.span_start, citation.span_end]
            
            # Get surrounding context if span information is available
            start_context = max(0, citation.span_start - 200)
            end_context = min(len(preprocessed_text), citation.span_end + 200)
            context = preprocessed_text[start_context:end_context]
            citation_info["context"] = context
            
            # Check for unpublished case patterns in the context
            unpublished_info = detect_unpublished_case(preprocessed_text, citation.span_start, 
                                                     citation.span_end - citation.span_start)
            
            if unpublished_info["is_unpublished"]:
                for key, value in unpublished_info.items():
                    citation_info[key] = value
        
        # Handle different citation types
        if hasattr(citation, 'year') and citation.year:
            citation_info["year"] = citation.year
            
        if hasattr(citation, 'volume') and citation.volume:
            citation_info["volume"] = citation.volume
            
        if hasattr(citation, 'reporter') and citation.reporter:
            citation_info["reporter"] = citation.reporter
            
        if hasattr(citation, 'page') and citation.page:
            citation_info["page"] = citation.page
            
        if hasattr(citation, 'groups') and citation.groups:
            citation_info["groups"] = citation.groups
            
        if hasattr(citation, 'court') and citation.court:
            citation_info["court"] = citation.court
        
        # For case citations, add plaintiff and defendant
        if hasattr(citation, 'metadata') and citation.metadata:
            metadata = citation.metadata
            
            # Create a lookup key for this citation to check if we have better metadata
            if hasattr(citation, 'reporter') and citation.reporter and \
               hasattr(citation, 'volume') and hasattr(citation, 'page'):
                citation_key = f"{citation.volume} {citation.reporter} {citation.page}"
                
                # Use our enhanced metadata from Table of Authorities if available
                if citation_key in known_case_titles:
                    if 'title' in known_case_titles[citation_key]:
                        citation_info["case_title"] = known_case_titles[citation_key]["title"]
                    if 'plaintiff' in known_case_titles[citation_key]:
                        citation_info["plaintiff"] = known_case_titles[citation_key]["plaintiff"]
                    if 'defendant' in known_case_titles[citation_key]:
                        citation_info["defendant"] = known_case_titles[citation_key]["defendant"]
                else:
                    # Use the default metadata
                    if hasattr(metadata, 'plaintiff') and metadata.plaintiff:
                        citation_info["plaintiff"] = metadata.plaintiff
                    if hasattr(metadata, 'defendant') and metadata.defendant:
                        citation_info["defendant"] = metadata.defendant
                    
                    # Try to extract case title from context if not already set
                    if not citation_info.get("case_title") and citation_info.get("context"):
                        span_start = citation.span_start
                        context = citation_info["context"]
                        citation_position = span_start - max(0, span_start - 200)
                        extracted_title = extract_case_title_from_context(context, citation_position)
                        if extracted_title:
                            citation_info["case_title"] = extracted_title
                            
                            # Extract plaintiff and defendant from title if not already set
                            if ' v. ' in extracted_title and not citation_info.get("plaintiff") and not citation_info.get("defendant"):
                                name_parts = extracted_title.split(' v. ')
                                if len(name_parts) == 2:
                                    citation_info["plaintiff"] = name_parts[0].strip()
                                    citation_info["defendant"] = name_parts[1].strip()
            else:
                # For other citations, use the default metadata
                if hasattr(metadata, 'plaintiff') and metadata.plaintiff:
                    citation_info["plaintiff"] = metadata.plaintiff
                if hasattr(metadata, 'defendant') and metadata.defendant:
                    citation_info["defendant"] = metadata.defendant
            
            # Handle pin cites (page pinpoint citations)
            if find_pinpoint_cites and hasattr(metadata, 'pin_cite') and metadata.pin_cite:
                citation_info["pin_cite"] = metadata.pin_cite
                citation_info["is_pinpoint"] = True
        
        # Create Google Scholar URL
        google_scholar_url = create_google_scholar_url(citation_info)
        if google_scholar_url:
            citation_info["google_scholar_url"] = google_scholar_url
        
        # Create court URL for certain citation types
        court_url = create_court_url(citation_info)
        if court_url:
            citation_info["court_url"] = court_url
        
        # Construct full case title for display if we have plaintiff and defendant
        if citation_info.get("plaintiff") and citation_info.get("defendant"):
            citation_info["full_title"] = f"{citation_info['plaintiff']} v. {citation_info['defendant']}"
        elif citation_info.get("case_title"):
            citation_info["full_title"] = citation_info["case_title"]
        
        structured_citations.append(citation_info)
    
    # If finding pinpoint citations is enabled, process short form and id citations
    if find_pinpoint_cites:
        # Identify short form citations that might be pinpoints to full citations
        for citation in raw_citations:
            if citation.__class__.__name__ in ["ShortCaseCitation", "IdCitation"]:
                if hasattr(citation, 'metadata') and citation.metadata and hasattr(citation.metadata, 'pin_cite') and citation.metadata.pin_cite:
                    citation_text = str(citation)
                    
                    # Skip if we've already seen this citation
                    if citation_text in seen_citations:
                        continue
                    seen_citations.add(citation_text)
                    
                    # Add as a pinpoint citation
                    pin_cite_info = {
                        "type": citation.__class__.__name__,
                        "text": citation_text,
                        "is_pinpoint": True,
                        "pin_cite": citation.metadata.pin_cite
                    }
                    
                    # Add span information if available
                    if hasattr(citation, 'span_start') and citation.span_start is not None and \
                       hasattr(citation, 'span_end') and citation.span_end is not None:
                        pin_cite_info["span"] = [citation.span_start, citation.span_end]
                        
                        # Get surrounding context
                        start_context = max(0, citation.span_start - 100)
                        end_context = min(len(preprocessed_text), citation.span_end + 100)
                        pin_cite_info["context"] = preprocessed_text[start_context:end_context]
                    
                    # For ShortCaseCitation, try to get the reporter and page
                    if citation.__class__.__name__ == "ShortCaseCitation" and hasattr(citation, 'groups') and citation.groups:
                        if 'volume' in citation.groups:
                            pin_cite_info["volume"] = citation.groups['volume']
                        if 'reporter' in citation.groups:
                            pin_cite_info["reporter"] = citation.groups['reporter']
                        if 'page' in citation.groups:
                            pin_cite_info["page"] = citation.groups['page']
                    
                    # Attempt to identify which full citation this pinpoint refers to
                    if citation.__class__.__name__ == "ShortCaseCitation" and hasattr(citation, 'antecedent_guess'):
                        pin_cite_info["antecedent_guess"] = citation.antecedent_guess
                        
                        # Find corresponding full citation based on name for display
                        for full_cite in structured_citations:
                            if full_cite.get("plaintiff") == citation.antecedent_guess or \
                               full_cite.get("defendant") == citation.antecedent_guess or \
                               (full_cite.get("case_title") and citation.antecedent_guess in full_cite.get("case_title")):
                                pin_cite_info["main_citation"] = full_cite
                                break
                    
                    structured_citations.append(pin_cite_info)
    
    return structured_citations

def process_file(file_path, find_pinpoint_cites=False, known_case_titles=None):
    """
    Process a file and extract citations with enhanced Table of Authorities parsing.
    """
    if known_case_titles is None:
        known_case_titles = {}
        
    try:
        path = Path(file_path)
        
        # Extract text based on file type
        if path.suffix.lower() == '.pdf':
            text = extract_text_from_pdf(file_path)
        elif path.suffix.lower() in ['.docx', '.doc']:
            text = extract_text_from_docx(file_path)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            except UnicodeDecodeError:
                # Try with a different encoding if UTF-8 fails
                try:
                    with open(file_path, 'r', encoding='latin-1') as file:
                        text = file.read()
                except Exception as e:
                    print(f"Error reading file with latin-1 encoding: {str(e)}")
                    return [], known_case_titles
        
        # Normalize whitespace while preserving paragraph breaks
        text = normalize_whitespace(text)
        
        # Save the cleaned text
        cleaned_path = save_cleaned_text(text, path)
        print(f"\nCleaned text saved to: {cleaned_path}")
        
        # Extract case data from Table of Authorities if available
        toa_case_data = extract_table_of_authorities(text)
        if toa_case_data:
            print(f"Found {len(toa_case_data)} citations in Table of Authorities")
            # Merge with any existing known case titles
            if known_case_titles is None:
                known_case_titles = {}
            known_case_titles.update(toa_case_data)
        
        # Extract citations from the full text
        citations = extract_case_citations(text, find_pinpoint_cites, known_case_titles)
        
        if citations:
            print(f"\nCitations found in {file_path}: {len(citations)}")
            for citation in citations[:5]:  # Show just a few examples
                case_info = ""
                if citation.get("full_title"):
                    case_info = f" ({citation['full_title']})"
                elif citation.get("plaintiff") and citation.get("defendant"):
                    case_info = f" ({citation['plaintiff']} v. {citation['defendant']})"
                
                print(f"[{citation['type']}] {citation['text']}{case_info}")
            
            if len(citations) > 5:
                print(f"... and {len(citations) - 5} more citations.")
        else:
            print(f"\nNo citations found in {file_path}")
            
        return citations, known_case_titles
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return [], known_case_titles

def generate_html_output(citations, file_path, known_case_titles=None):
    """
    Generate HTML output for the citations, grouped by reporter with pinpoint
    citations displayed inline and compact vertical layout.
    """
    if known_case_titles is None:
        known_case_titles = {}
    
    # Group citations by reporter
    citations_by_reporter = defaultdict(list)
    
    # First, identify and group the primary citations (not pinpoints)
    main_citations = []
    pinpoint_citations = []
    
    for citation in citations:
        if citation.get("is_pinpoint"):
            pinpoint_citations.append(citation)
        else:
            main_citations.append(citation)
            
            # Group by reporter
            reporter = citation.get("reporter", "Other")
            if citation.get("is_unpublished"):
                if citation.get("wl_cite"):
                    reporter = "Westlaw (Unpublished)"
                else:
                    reporter = "Unpublished"
            
            citations_by_reporter[reporter].append(citation)
    
    # Sort reporters alphabetically, but put standard reporters first
    priority_reporters = ["U.S.", "S.Ct.", "L.Ed.", "S.W.", "S.W.2d", "S.W.3d", "F.", "F.2d", "F.3d", "F.4th"]
    
    sorted_reporters = sorted(citations_by_reporter.keys(), 
                            key=lambda r: (-100 if r in priority_reporters else 
                                         (-50 if "Unpublished" in r else 
                                          priority_reporters.index(r) if r in priority_reporters else 100)))
    
    # Map pinpoint citations to their main citations
    pinpoint_dict = defaultdict(list)
    for pin in pinpoint_citations:
        # For short citations, try to find the corresponding full citation
        if pin.get("antecedent_guess"):
            for main in main_citations:
                if main.get("plaintiff") == pin.get("antecedent_guess") or \
                   main.get("defendant") == pin.get("antecedent_guess") or \
                   (main.get("case_title") and pin.get("antecedent_guess") in main.get("case_title")):
                    pinpoint_dict[main["text"]].append(pin)
                    break
        
        # For ID citations, the previous citation is the parent
        if pin.get("type") == "IdCitation" and len(main_citations) > 0:
            # Associate with the most recent main citation
            pinpoint_dict[main_citations[-1]["text"]].append(pin)
    
    # Create HTML content
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Citations from {os.path.basename(file_path)}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        h1 {{ color: #333; border-bottom: 1px solid #ddd; padding-bottom: 10px; }}
        h2 {{ color: #444; margin-top: 20px; }}
        h3 {{ color: #555; margin-top: 15px; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
        th, td {{ text-align: left; padding: 8px; vertical-align: top; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .context {{ font-style: italic; color: #666; font-size: 0.9em; margin-top: 5px; }}
        .case-name {{ font-weight: bold; }}
        .citation-details {{ color: #555; }}
        .pinpoint {{ font-size: 0.9em; color: #666; margin-left: 15px; }}
        .google-scholar-link {{ color: #1a0dab; text-decoration: none; margin-left: 10px; }}
        .google-scholar-link:hover {{ text-decoration: underline; }}
        .court-link {{ color: #0d6efd; text-decoration: none; margin-left: 10px; }}
        .court-link:hover {{ text-decoration: underline; }}
        .pin-cite {{ color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <h1>Citations Extracted from {os.path.basename(file_path)}</h1>
    <p>Total citations found: {len(citations)}</p>
"""

    # Add sections for each reporter
    for reporter in sorted_reporters:
        reporter_citations = citations_by_reporter[reporter]
        
        html_content += f"""
    <h2>{reporter} ({len(reporter_citations)})</h2>
    <table>
        <tr>
            <th>Citation</th>
            <th>Links</th>
        </tr>
"""
        
        # Sort citations by case title if available, otherwise by citation text
        reporter_citations.sort(key=lambda c: c.get("full_title", c.get("case_title", c.get("text", ""))))
        
        for citation in reporter_citations:
            # Generate the citation display HTML
            citation_display = ""
            case_title_html = ""
            
            # For full case citations with title
            if citation.get("full_title"):
                case_title_html = f'<div class="case-name">{html.escape(citation["full_title"])}</div>'
            elif citation.get("case_title"):
                case_title_html = f'<div class="case-name">{html.escape(citation["case_title"])}</div>'
            elif citation.get("plaintiff") and citation.get("defendant"):
                case_title_html = f'<div class="case-name">{html.escape(citation["plaintiff"])} v. {html.escape(citation["defendant"])}</div>'
            
            # Citation details
            citation_details = ""
            
            if citation.get("is_unpublished") and citation.get("wl_cite"):
                # WL citation
                citation_details = f'<div class="citation-details">{html.escape(citation["wl_cite"])}</div>'
                if citation.get("case_number"):
                    citation_details += f' <span class="pin-cite">No. {html.escape(citation["case_number"])}</span>'
            elif citation.get("is_unpublished") and citation.get("case_number"):
                # Unpublished with cause number only
                citation_details = f'<div class="citation-details">No. {html.escape(citation["case_number"])}</div>'
            else:
                # Standard citation
                volume = html.escape(str(citation.get("volume", "")))
                reporter = html.escape(str(citation.get("reporter", "")))
                page = html.escape(str(citation.get("page", "")))
                year = html.escape(str(citation.get("year", "")))
                
                if volume and reporter and page:
                    citation_details = f'<div class="citation-details">{volume} {reporter} {page}'
                    if year:
                        citation_details += f' ({year})'
                    citation_details += '</div>'
                else:
                    # Fallback to just the citation text
                    citation_details = f'<div class="citation-details">{html.escape(str(citation.get("text", "")))}</div>'
            
            citation_display = case_title_html + citation_details
            
            # Add pinpoint citations if any exist for this citation
            if citation["text"] in pinpoint_dict:
                pinpoints = pinpoint_dict[citation["text"]]
                pinpoint_display = '<div class="pinpoint">Pinpoint citations: '
                pin_cites = []
                
                for pin in pinpoints:
                    if pin.get("pin_cite"):
                        pin_cites.append(f'<span class="pin-cite">{html.escape(str(pin["pin_cite"]))}</span>')
                
                if pin_cites:
                    pinpoint_display += ', '.join(pin_cites)
                    pinpoint_display += '</div>'
                    citation_display += pinpoint_display
            
            # Generate links column
            links_html = ""
            
            # Add Google Scholar link if available
            if citation.get("google_scholar_url"):
                links_html += f'<a href="{citation["google_scholar_url"]}" target="_blank" class="google-scholar-link">Google Scholar</a>'
            
            # Add court website link if available
            if citation.get("court_url"):
                links_html += f'<a href="{citation["court_url"]}" target="_blank" class="court-link">Court Website</a>'
            
            # If no links available
            if not links_html:
                links_html = "N/A"
            
            html_content += f"""
        <tr>
            <td>{citation_display}</td>
            <td>{links_html}</td>
        </tr>
"""
        
        html_content += """
    </table>
"""
    
    html_content += """
</body>
</html>
"""
    
    return html_content

def save_custom_citations(citations, output_path):
    """Save extracted custom citation data to a JSON file."""
    custom_citations = []
    
    for citation in citations:
        if citation["type"] == "FullCaseCitation":
            custom_citation = {
                "type": "CustomCitation",
                "plaintiff": citation.get("plaintiff", None),
                "defendant": citation.get("defendant", None),
                "volume": citation.get("volume", None),
                "reporter": citation.get("reporter", None),
                "page": citation.get("page", None),
                "court": citation.get("year", None),
                "year": None,
                "text": citation.get("text", ""),
                "context": citation.get("context", ""),
                "full_citation": f"{citation.get('plaintiff', '')} v. {citation.get('defendant', '')}, {citation.get('volume', '')} {citation.get('reporter', '')} {citation.get('page', '')} ({citation.get('year', '')} {citation.get('court', '')})"
            }
            custom_citations.append(custom_citation)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(custom_citations, f, indent=2)
    
    print(f"Custom citations saved to {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Extract legal citations using eyecite')
    parser.add_argument('files', metavar='FILE', type=str, nargs='+',
                      help='Files to process')
    parser.add_argument('--json', action='store_true',
                      help='Output in JSON format')
    parser.add_argument('--html', action='store_true',
                      help='Generate HTML output')
    parser.add_argument('--output', '-o', type=str,
                      help='Output file for JSON or HTML results')
    parser.add_argument('--pinpoint', action='store_true',
                      help='Find and include pinpoint citations')
    parser.add_argument('--custom', action='store_true',
                      help='Save custom citation data (simplified format)')
    parser.add_argument('--custom-output', type=str, default='custom_citations.json',
                      help='Output file for custom citation data')
    parser.add_argument('--reporter-groups', action='store_true',
                      help='Group citations by reporter in HTML output')
    parser.add_argument('--debug', action='store_true',
                      help='Print detailed information about each citation')
    
    args = parser.parse_args()
    
    all_citations = []
    known_case_titles = {}
    
    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: {file_path} does not exist")
            continue
            
        file_citations, known_case_titles = process_file(file_path, args.pinpoint, known_case_titles)
        for citation in file_citations:
            citation["file"] = file_path
            all_citations.append(citation)
    
    if args.debug and all_citations:
        print("\nDebug information:")
        for citation in all_citations[:5]:  # Show just the first few for clarity
            print(f"\nCitation: {citation['text']}")
            for key, value in citation.items():
                if key not in ['text', 'context']:
                    print(f"  {key}: {value}")
    
    if args.html or (args.output and args.output.lower().endswith('.html')):
        output_file = args.output if args.output else "citations.html"
        
        # Generate HTML with citations organized by reporter
        html_content = generate_html_output(all_citations, args.files[0] if args.files else "unknown", known_case_titles)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"HTML output written to {output_file}")
    elif args.json or args.output:
        json_output = json.dumps(all_citations, indent=2, default=str)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(json_output)
            print(f"Results written to {args.output}")
        else:
            print(json_output)
    else:
        print(f"\nTotal citations found: {len(all_citations)}")
    
    # Save custom citation data if requested
    if args.custom and all_citations:
        custom_output = args.custom_output
        # If a directory was provided for --output, use it for custom output as well
        if args.output and os.path.isdir(os.path.dirname(args.output)):
            custom_output = os.path.join(os.path.dirname(args.output), custom_output)
        save_custom_citations(all_citations, custom_output)

if __name__ == "__main__":
    main()