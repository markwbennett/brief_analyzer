#!./.venv/bin/python

import re
import sys
import sqlite3
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from citations_db import CitationDB, ExtendedCitation

def clean_text(text):
    # Remove lines that are just page numbers (roman or arabic numerals)
    lines = text.split('\n')
    cleaned_lines = []
    
    # Roman numeral pattern for page numbers
    roman_pattern = re.compile(r'^[ivxlcdm]+$', re.IGNORECASE)
    # Arabic numeral pattern for page numbers
    arabic_pattern = re.compile(r'^\d+$')
    # Subheading pattern - lines containing only alphabetical characters and spaces
    subheading_pattern = re.compile(r'^[A-Za-z\s]+$')
    
    for line in lines:
        # Skip lines that are just Roman or Arabic numerals (page numbers)
        # or are all alphabetic (subheadings)
        stripped = line.strip()
        if roman_pattern.match(stripped) or arabic_pattern.match(stripped) or subheading_pattern.match(stripped):
            continue
            
        # For non-empty lines, add them
        if stripped:
            cleaned_lines.append(stripped)
    
    # Recombine the text after removing page numbers and subheadings
    text = '\n'.join(cleaned_lines)
    
    # Replace strings of periods and spaces between any visible characters with a tab
    text = re.sub(r'(?<=\S)[\s.]{4,}(?=\S)', '\t', text)
    
    # Collapse consecutive spaces but preserve tabs and new-line structure
    text = re.sub(r' +', ' ', text)
    
    # Convert non-digit character followed by newline to char + space + newline
    text = re.sub(r'([^\d])\n', r'\1 ', text)
    
    # Convert newline-parenthesis sequences to space-parenthesis
    text = re.sub(r'\s*\n\(', ' (', text)
    
    return text

def consolidate_citations(citations):
    # Group citations by case (using plaintiff/defendant)
    case_groups = {}
    for citation in citations:
        key = (citation.plaintiff, citation.defendant)
        if key not in case_groups:
            case_groups[key] = []
        case_groups[key].append(citation)
    
    # For each case, determine primary and alternative citations
    consolidated = []
    for citations in case_groups.values():
        if not citations:
            continue
            
        # Sort by reporter preference (U.S. > S.Ct. > L.Ed.)
        def reporter_rank(citation):
            if 'U.S.' in citation.reporter:
                return 0
            elif 'S.Ct.' in citation.reporter or 'S. Ct.' in citation.reporter:
                return 1
            elif 'L.Ed.' in citation.reporter or 'L. Ed.' in citation.reporter:
                return 2
            return 3
            
        citations.sort(key=reporter_rank)
        
        # Primary citation is first in sorted list
        primary = citations[0]
        
        # Add alternative citations, deduplicating by volume+reporter+page
        seen = {(primary.volume, primary.reporter, primary.page)}
        alt_citations = []
        for citation in citations[1:]:
            key = (citation.volume, citation.reporter, citation.page)
            if key not in seen:
                seen.add(key)
                alt_citations.append(citation)
        
        primary.alt_citations = alt_citations
        consolidated.append(primary)
    
    return consolidated

def extract_cause_number(text):
    # Generic pattern to match anything between "No. " and comma
    match = re.search(r'No\.\s+([\w\-,]+?)(?:,|$)', text)
    if match:
        return match.group(1).strip()
    return None

def extract_alt_cite(text):
    # After cause number and comma
    lexis_pattern = r',\s*(\d{4}\s+\w+\s+LEXIS\s+\d+)'
    wl_pattern = r',\s*(\d{4}\s+WL\s+\d+)'
    
    lexis_match = re.search(lexis_pattern, text)
    if lexis_match:
        return lexis_match.group(1)
        
    wl_match = re.search(wl_pattern, text)
    if wl_match:
        return wl_match.group(1)
        
    return None

def extract_page_numbers(text):
    # After tab, comma-separated numbers
    match = re.search(r'\t([\d,\s]+)$', text)
    if match:
        return [int(p.strip()) for p in match.group(1).split(',')]
    return []

def find_toa_boundaries(text):
    """Return (start_idx, end_idx) for Table/Index of Authorities section.

    Strategy:
    1. Parse the table-of-contents (TOC) to discover which section immediately
       follows the TOA/IOA entry.  This is done by
         • finding the line "TABLE OF CONTENTS".
         • collecting subsequent lines that contain dot-leaders ending in a page number.
    2. Within those TOC lines find the entry whose title is TABLE/INDEX OF
       AUTHORITIES; grab the *next* entry title — that is the header that follows
       the TOA in the main brief (e.g. "STATEMENT OF ORAL ARGUMENT").
    3. In the main text locate the TOA header ("TABLE/INDEX OF AUTHORITIES").
    4. Scan forward until the line whose text begins with that next-section title;
       the line before it marks the end of the TOA.
    5. If parsing the TOC or locating the follow-on header fails, fall back to a
       simpler heuristic: keep updating the last dot-leader line and stop once ten
       successive non-entry lines have been seen.
    """

    lines = text.split('\n')

    # --- helper regexes ---
    toc_header_re = re.compile(r'^TABLE\s+OF\s+CONTENTS\s*$', re.IGNORECASE)
    toc_entry_re = re.compile(r'^\s*(?P<title>.*?)\s+\.{3,}\s*(?P<page>\d+)\s*$')
    toa_entry_re = re.compile(r'^(?:TABLE|INDEX)\s+OF\s+AUTHORITIES$', re.IGNORECASE)

    # 1) harvest TOC entries
    toc_entries = []  # list of (title,line_idx)
    in_toc = False
    for idx, ln in enumerate(lines):
        stripped = ln.strip()
        if not in_toc and toc_header_re.match(stripped):
            in_toc = True
            continue
        if in_toc:
            m = toc_entry_re.match(stripped)
            if m:
                title = m.group('title').strip()
                toc_entries.append((title, idx))
            else:
                # stop once we leave block of dot-leader lines after at least one entry seen
                if toc_entries:
                    break

    # 2) determine the title that follows TOA inside TOC
    next_section_title = None
    for i, (title, _) in enumerate(toc_entries):
        if toa_entry_re.match(title):
            if i + 1 < len(toc_entries):
                next_section_title = toc_entries[i + 1][0]
            break

    # compile regex for next section header if available
    next_header_re = re.compile(r'^' + re.escape(next_section_title) + r'\b', re.IGNORECASE) if next_section_title else None

    # 3) locate TOA header in body
    start_idx = None
    body_toa_header_re = toa_entry_re  # same pattern but already compiled
    for idx, ln in enumerate(lines):
        if body_toa_header_re.match(ln.strip()):
            start_idx = idx
            break
    if start_idx is None:
        return None, None

    # 4) primary approach: use next_header_re to find end
    if next_header_re is not None:
        for idx in range(start_idx + 1, len(lines)):
            stripped = lines[idx].strip()
            if next_header_re.match(stripped):
                return start_idx, idx - 1

    # 5) fallback heuristic (dot-leader gap)
    # Dot leader is simply 5+ consecutive periods followed by a digit (with optional space)
    dot_re = re.compile(r'\.{5,}\s*\d')
    # Fallback: end TOA after 10 successive non dot-leader lines following the last dot-leader entry.

    last_dot_idx = None
    gap_without_dot = 0
    for idx in range(start_idx + 1, len(lines)):
        stripped = lines[idx].strip()

        # leader resets gap counter
        if dot_re.search(stripped):
            last_dot_idx = idx
            gap_without_dot = 0
            continue

        # otherwise count non-leader line
        gap_without_dot += 1
        # stop after 10 successive non-dot lines
        if gap_without_dot >= 10 and last_dot_idx is not None:
            return start_idx, last_dot_idx

    return start_idx, last_dot_idx

def find_argument_boundaries(text):
    lines = text.split('\n')
    start_idx = None
    end_idx = None
    
    # Find start - look for "ARGUMENT" or "ARGUMENT AND AUTHORITIES" header
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^(?:ARGUMENT|ARGUMENT\s+AND\s+AUTHORITIES)\s*$', stripped, re.IGNORECASE) and not re.search(r'\.{3,}\s*\d+\s*$', stripped):
            start_idx = i
            break
            
    if start_idx is None:
        return None, None
        
    # Find end - look for "PRAYER" header
    for i in range(start_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'^PRAYER\s*$', stripped, re.IGNORECASE) and not re.search(r'\.{3,}\s*\d+\s*$', stripped):
            end_idx = i
            break
            
    return start_idx, end_idx

def extract_table_of_authorities(text):
    # Look for TABLE OF AUTHORITIES section
    toa_pattern = r"TABLE OF AUTHORITIES.*?(?=STATEMENT OF ORAL ARGUMENT|STATEMENT OF THE CASE)"
    toa_match = re.search(toa_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if toa_match:
        toa_text = toa_match.group(0)
        return clean_text(toa_text)
    return None

def find_citations(text, doc_name):
    citations = get_citations(text)
    results = []
    
    conn = sqlite3.connect('citations.db')
    c = conn.cursor()
    
    # Drop existing tables to ensure schema is correct
    c.execute('DROP TABLE IF EXISTS appearances')
    c.execute('DROP TABLE IF EXISTS page_references')
    c.execute('DROP TABLE IF EXISTS alternative_citations')
    c.execute('DROP TABLE IF EXISTS citations')
    
    # Create tables with updated schema
    c.execute('''CREATE TABLE citations
                 (id INTEGER PRIMARY KEY,
                  full_cite TEXT,
                  case_title TEXT,
                  volume TEXT,
                  reporter TEXT,
                  page TEXT,
                  year TEXT,
                  court TEXT,
                  plaintiff TEXT,
                  defendant TEXT,
                  publication_status TEXT,
                  doc_name TEXT,
                  lexis_cite TEXT,
                  westlaw_cite TEXT,
                  cause_number TEXT,
                  subsequent_history TEXT,
                  short_cite TEXT)''')
                  
    c.execute('''CREATE TABLE alternative_citations
                 (id INTEGER PRIMARY KEY,
                  citation_id INTEGER,
                  alt_cite TEXT,
                  volume TEXT,
                  reporter TEXT,
                  page TEXT,
                  FOREIGN KEY(citation_id) REFERENCES citations(id))''')
                  
    c.execute('''CREATE TABLE appearances
                 (id INTEGER PRIMARY KEY,
                  citation_id INTEGER,
                  line_number INTEGER,
                  doc_name TEXT,
                  FOREIGN KEY(citation_id) REFERENCES citations(id))''')
                  
    c.execute('''CREATE TABLE page_references
                 (id INTEGER PRIMARY KEY,
                  citation_id INTEGER,
                  page_number INTEGER,
                  doc_name TEXT,
                  FOREIGN KEY(citation_id) REFERENCES citations(id))''')

    # Dictionary to keep track of citations we've already seen
    seen_citations = {}

    text_lines = text.split('\n')
    for i, line in enumerate(text_lines):
        # Process each line to find citations
        line_citations = get_citations(line)
        
        # Extract page numbers that follow the tab character in this line
        page_numbers = []
        tab_split = line.split('\t')
        if len(tab_split) > 1:
            # Get the text after the tab and parse page numbers
            page_text = tab_split[1].strip()
            # Extract comma-separated page numbers
            for page in page_text.split(','):
                try:
                    page_numbers.append(int(page.strip()))
                except ValueError:
                    # Skip if not a number
                    continue
        
        for citation in line_citations:
            if isinstance(citation, FullCaseCitation):
                # Extract basic citation info from eyecite
                volume = citation.groups.get('volume')
                reporter = citation.groups.get('reporter')
                page = citation.groups.get('page')
                
                if not volume or not reporter or not page:
                    continue
                
                # Create a properly formatted full citation
                full_cite = f"{volume} {reporter} {page}"
                
                # Get the citation text and surrounding context
                citation_span = line
                
                # Use our own logic to extract other fields
                year = None
                year_match = re.search(r'\((\d{4})\)', citation_span)
                if year_match:
                    year = year_match.group(1)
                
                # Extract plaintiff and defendant from context
                parties = citation_span.split(full_cite)[0].strip() if full_cite in citation_span else ""
                plaintiff = None
                defendant = None
                
                # Extract case title from beginning of line to first comma if available
                case_title = None
                if ',' in citation_span:
                    case_title = citation_span.split(',')[0].strip()
                
                party_match = re.search(r'([^,]+)\s+v\.\s+([^,]+)', parties)
                if party_match:
                    plaintiff = party_match.group(1).strip()
                    defendant = party_match.group(2).strip()
                    if not case_title:
                        case_title = f"{plaintiff} v. {defendant}" if plaintiff and defendant else None
                
                # If still no case title, try to extract from the beginning of the line
                if not case_title and citation_span:
                    case_title = citation_span.split(',')[0].strip() if ',' in citation_span else None
                
                # Determine court based on reporter
                court = None
                if reporter == 'U.S.':
                    court = 'scotus'
                elif reporter == 'F.3d' or reporter == 'F.2d':
                    court = 'ca'
                elif reporter == 'S.Ct.' or reporter == 'S. Ct.':
                    court = 'scotus'
                
                # Initialize LEXIS and Westlaw cite fields
                lexis_cite = None
                westlaw_cite = None
                cause_number = None
                subsequent_history = None
                short_cite = None
                
                # Determine if this is an unpublished case
                is_unpublished = False
                
                # Check for LEXIS citation
                if 'LEXIS' in reporter:
                    is_unpublished = True
                    lexis_cite = f"{volume} {reporter} {page}"
                    # Extract cause number with improved regex to handle both No. and Nos.
                    cause_match = re.search(r'No(?:s?\.)?\s+([\w\-.,\s]+?)(?:,|$)', citation_span)
                    if cause_match:
                        cause_number = cause_match.group(1).strip()
                        # For multiple cause numbers, take only the first one
                        if ',' in cause_number:
                            cause_number = cause_number.split(',')[0].strip()
                        # Update full_cite to use cause number
                        full_cite = f"No. {cause_number}"
                    # Clear the regular citation fields
                    volume = None
                    reporter = None
                    page = None
                
                # Check for Westlaw citation
                elif reporter == 'WL':
                    is_unpublished = True
                    westlaw_cite = f"{volume} {reporter} {page}"
                    # Extract cause number with improved regex to handle both No. and Nos.
                    cause_match = re.search(r'No(?:s?\.)?\s+([\w\-.,\s]+?)(?:,|$)', citation_span)
                    if cause_match:
                        cause_number = cause_match.group(1).strip()
                        # For multiple cause numbers, take only the first one
                        if ',' in cause_number:
                            cause_number = cause_number.split(',')[0].strip()
                        # Update full_cite to use cause number
                        full_cite = f"No. {cause_number}"
                    # Clear the regular citation fields
                    volume = None
                    reporter = None
                    page = None
                
                # Extract subsequent history if available
                subsequent_match = re.search(r',\s*(?:cert\.|certiorari|aff\'[dg]|rev\'[dg]|vacated|remanded|denied).*?(?=$|;)', citation_span, re.IGNORECASE)
                if subsequent_match:
                    subsequent_history = subsequent_match.group(0).strip(', ')
                
                # Generate short cite based on the rules
                if case_title:
                    # Determine short name
                    short_name = case_title
                    
                    # Rule 1: State v. X or X v. State -> X
                    state_match = re.search(r'(.*?)\s+v\.\s+(State|United States|U\.S\.)', case_title, re.IGNORECASE)
                    if state_match:
                        short_name = state_match.group(1).strip()
                    else:
                        state_match = re.search(r'(State|United States|U\.S\.)\s+v\.\s+(.*)', case_title, re.IGNORECASE)
                        if state_match:
                            short_name = state_match.group(2).strip()
                    
                    # Rule 2: In re X or Ex parte X -> X
                    in_re_match = re.search(r'(?:In re|Ex parte)\s+(.*)', case_title, re.IGNORECASE)
                    if in_re_match:
                        short_name = in_re_match.group(1).strip()
                    
                    # Format the short cite based on published/unpublished status
                    if not is_unpublished and volume and reporter:
                        short_cite = f"{short_name}, {volume} {reporter}"
                    else:
                        # Prefer Westlaw over LEXIS
                        if westlaw_cite:
                            short_cite = f"{short_name}, {westlaw_cite}"
                        elif lexis_cite:
                            short_cite = f"{short_name}, {lexis_cite}"
                
                # Check if we've already seen this citation
                if full_cite in seen_citations:
                    citation_id = seen_citations[full_cite]
                else:
                    # Insert main citation
                    c.execute('''INSERT INTO citations 
                                (full_cite, case_title, volume, reporter, page, year, court, 
                                 plaintiff, defendant, publication_status, doc_name,
                                 lexis_cite, westlaw_cite, cause_number, subsequent_history, short_cite)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                             (full_cite, case_title,
                              volume, reporter, page, year, court, plaintiff, defendant,
                              'unpublished' if is_unpublished else 'published', doc_name,
                              lexis_cite, westlaw_cite, cause_number, subsequent_history, short_cite))
                    
                    citation_id = c.lastrowid
                    seen_citations[full_cite] = citation_id
                    
                    # Find alternative citations by looking for other citations on the same line
                    other_citations = [c for c in line_citations if c != citation and isinstance(c, FullCaseCitation)]
                    for alt_citation in other_citations:
                        alt_volume = alt_citation.groups.get('volume')
                        alt_reporter = alt_citation.groups.get('reporter')
                        alt_page = alt_citation.groups.get('page')
                        
                        if alt_volume and alt_reporter and alt_page:
                            alt_cite = f"{alt_volume} {alt_reporter} {alt_page}"
                            c.execute('''INSERT INTO alternative_citations
                                        (citation_id, alt_cite, volume, reporter, page)
                                        VALUES (?, ?, ?, ?, ?)''',
                                    (citation_id, alt_cite, alt_volume, alt_reporter, alt_page))
                
                # Record the line where this citation appears
                c.execute('''INSERT INTO appearances
                            (citation_id, line_number, doc_name)
                            VALUES (?, ?, ?)''',
                         (citation_id, i + 1, doc_name))
                
                # Record the page numbers if this is a TOA entry
                if page_numbers:
                    for page_num in page_numbers:
                        c.execute('''INSERT INTO page_references
                                    (citation_id, page_number, doc_name)
                                    VALUES (?, ?, ?)''',
                                 (citation_id, page_num, doc_name))
    
    conn.commit()
    conn.close()
    return results

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using pdfminer.six with improved whitespace handling."""
    try:
        from pdfminer.high_level import extract_text as pdf_extract_text
        # Extract raw text
        text = pdf_extract_text(pdf_path)
        # Normalize whitespace while preserving important line breaks
        text = re.sub(r' {2,}', ' ', text)  # Replace multiple spaces with single space
        text = re.sub(r'\n{3,}', '\n\n', text)  # Replace multiple newlines with double newline
        return text
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")

# Helper to collapse runs of more than two consecutive line feeds down to exactly two
def compress_newlines(text: str) -> str:
    """Iteratively replace three-or-more consecutive newlines with exactly two until
    no such runs remain. This preserves paragraph breaks (double newlines) while
    removing superfluous blank lines that can interfere with section detection
    (e.g., TABLE OF AUTHORITIES / INDEX OF AUTHORITIES boundaries)."""
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    return text

def main():
    if len(sys.argv) < 2:
        print("Usage: extract_authorities.py <pdf_file>")
        return
        
    pdf_file = sys.argv[1]
    base_name = pdf_file.split('/')[-1].split('.')[0]
    
    # Extract raw text from PDF
    raw_text = extract_text_from_pdf(pdf_file)
    
    # Save the raw text for debugging
    debug_file = f"{base_name}_debug_raw.txt"
    with open(debug_file, 'w') as f:
        f.write(raw_text)
    print(f"Raw text saved for debugging: {debug_file}")
    
    # Remove whitespace from beginning of lines
    lines = raw_text.split('\n')
    lines = [line.lstrip() for line in lines]
    raw_text = '\n'.join(lines)
    
    # Normalize consecutive blank lines to maximum of two
    while '\n\n\n' in raw_text:
        raw_text = raw_text.replace('\n\n\n', '\n\n')

    # Save the full text output
    output_file = f"{base_name}.txt"
    with open(output_file, 'w') as f:
        f.write(raw_text)
    
    # Find and extract Table of Authorities section
    toa_start, toa_end = find_toa_boundaries(raw_text)
    if toa_start is not None and toa_end is not None:
        toa_text = '\n'.join(raw_text.split('\n')[toa_start:toa_end+1])
        raw_toa_file = f"{base_name}_toa_raw.txt"
        with open(raw_toa_file, 'w') as f:
            f.write(toa_text)
        print(f"Raw Table of Authorities saved to: {raw_toa_file}")
        
        # Clean up and save the cleaned version
        cleaned_toa = clean_text(toa_text)
        cleaned_toa_file = f"{base_name}_toa_cleaned.txt"
        with open(cleaned_toa_file, 'w') as f:
            f.write(cleaned_toa)
        print(f"Cleaned Table of Authorities saved to: {cleaned_toa_file}")
        
        # Find citations in the cleaned TOA only
        find_citations(cleaned_toa, base_name)
    else:
        print("No Table of Authorities found")
    
    
    # Find and extract Argument section
    arg_start, arg_end = find_argument_boundaries(raw_text)
    if arg_start is not None and arg_end is not None:
        arg_text = '\n'.join(raw_text.split('\n')[arg_start:arg_end+1])
        arg_file = f"{base_name}_argument.txt"
        with open(arg_file, 'w') as f:
            f.write(clean_text(arg_text))
        print(f"Argument section saved to: {arg_file}")
    else:
        print("No Argument section found")
        
    # Get citation count from database
    conn = sqlite3.connect('citations.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM citations")
    citation_count = cursor.fetchone()[0]
    
    # Fetch all citation data with line numbers and new fields
    cursor.execute("""
        SELECT c.id, c.full_cite, c.case_title, c.volume, c.reporter, c.page, c.year, c.court, c.doc_name,
               a.line_number, c.lexis_cite, c.westlaw_cite, c.cause_number, c.subsequent_history, c.short_cite
        FROM citations c
        LEFT JOIN appearances a ON c.id = a.citation_id
        ORDER BY c.id, a.line_number
    """)
    all_citations = cursor.fetchall()
    
    # Format and save to a .txt file
    db_output_file = f"{base_name}_citations_db.txt"
    with open(db_output_file, 'w') as f:
        for citation in all_citations:
            # SQL columns now include new fields
            f.write(f"Citation ID: {citation[0]}, Full Cite: {citation[1]}, Case Title: {citation[2]}, " +
                    f"Volume: {citation[3]}, Reporter: {citation[4]}, Page: {citation[5]}, Year: {citation[6]}, " +
                    f"Court: {citation[7]}, Line Number: {citation[9]}, Doc Name: {citation[8]}, " +
                    f"LEXIS Cite: {citation[10]}, Westlaw Cite: {citation[11]}, Cause Number: {citation[12]}, " +
                    f"Subsequent History: {citation[13]}, Short Cite: {citation[14]}\n")
    
    print(f"Found {citation_count} citations")
    print(f"Citations saved to: {output_file}")
    print(f"Database citations saved to: {db_output_file}")

if __name__ == "__main__":
    main() 