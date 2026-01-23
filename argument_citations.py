#!/usr/bin/env python3
"""
Extract citations from the argument section of a legal brief PDF and generate
clickable CourtListener links for each citation.
"""

import re
import sys
import html
import time
import requests
from pathlib import Path
from urllib.parse import quote_plus
from dataclasses import dataclass, field
from eyecite import get_citations
from eyecite.models import FullCaseCitation, ShortCaseCitation
from pdfminer.high_level import extract_text as pdf_extract_text

# CourtListener API configuration
COURTLISTENER_API_TOKEN = "b6bc45c46b6507dcde53992ef3523e46e5a9e3ed"
COURTLISTENER_API_BASE = "https://www.courtlistener.com/api/rest/v4"


@dataclass
class CitationLink:
    """Represents a citation with its link."""
    case_name: str
    full_citation: str
    volume: str
    reporter: str
    page: str
    pinpoint: str | None
    year: str | None
    courtlistener_url: str | None
    scholar_url: str  # fallback
    preceding_sentence: str
    position: int  # position in document for ordering


# Cache for CourtListener lookups to avoid duplicate API calls
_cl_cache: dict[str, str | None] = {}


def lookup_courtlistener(volume: str, reporter: str, page: str) -> str | None:
    """Look up a citation on CourtListener and return the opinion URL."""
    cache_key = f"{volume}|{reporter}|{page}"
    if cache_key in _cl_cache:
        return _cl_cache[cache_key]

    citation_str = f"{volume} {reporter} {page}"

    headers = {
        "Authorization": f"Token {COURTLISTENER_API_TOKEN}",
    }

    try:
        # Use the citation-lookup API v4 (POST with text parameter)
        response = requests.post(
            "https://www.courtlistener.com/api/rest/v4/citation-lookup/",
            data={"text": citation_str},
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Response is a list of citation results
        if data and len(data) > 0:
            result = data[0]
            if result.get("status") == 200 and result.get("clusters"):
                cluster = result["clusters"][0]
                absolute_url = cluster.get("absolute_url")
                if absolute_url:
                    url = f"https://www.courtlistener.com{absolute_url}"
                    _cl_cache[cache_key] = url
                    return url

        _cl_cache[cache_key] = None
        return None

    except Exception as e:
        print(f"  CourtListener lookup failed for {citation_str}: {e}", file=sys.stderr)
        _cl_cache[cache_key] = None
        return None


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file."""
    text = pdf_extract_text(pdf_path)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def find_argument_boundaries(text: str) -> tuple[int | None, int | None]:
    """Find the start and end line indices of the Argument section."""
    lines = text.split('\n')
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^(?:ARGUMENT|ARGUMENT\s+AND\s+AUTHORITIES)\s*$', stripped, re.IGNORECASE):
            if not re.search(r'\.{3,}\s*\d+\s*$', stripped):
                start_idx = i
                break

    if start_idx is None:
        return None, None

    for i in range(start_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'^(?:PRAYER|CONCLUSION)\s*$', stripped, re.IGNORECASE):
            if not re.search(r'\.{3,}\s*\d+\s*$', stripped):
                end_idx = i
                break

    return start_idx, end_idx


def build_scholar_url(volume: str, reporter: str, page: str, pinpoint: str | None = None) -> str:
    """Build a Google Scholar search URL for a case citation (fallback)."""
    reporter_normalized = reporter.replace('.', ' ').strip()
    if pinpoint and pinpoint != page:
        query = f'"{volume} {reporter_normalized} {page}" "{pinpoint}"'
    else:
        query = f'"{volume} {reporter_normalized} {page}"'
    return f"https://scholar.google.com/scholar?hl=en&as_sdt=6&q={quote_plus(query)}"


def extract_pinpoint(citation_text: str, base_page: str) -> str | None:
    """Extract pinpoint page reference from citation text."""
    pinpoint_patterns = [
        r',\s*(\d+)(?:\s*[-–]\s*\d+)?(?:\s|$|[,;)])',
        r'\bat\s+(\d+)',
    ]
    for pattern in pinpoint_patterns:
        match = re.search(pattern, citation_text)
        if match:
            pinpoint = match.group(1)
            if pinpoint != base_page:
                return pinpoint
    return None


def get_preceding_sentence(text: str, cite_start: int) -> str:
    """Extract the complete sentence that contains or precedes the citation."""
    # Get text before the citation (enough to find a full sentence)
    start_pos = max(0, cite_start - 1000)
    before_text = text[start_pos:cite_start]

    # Also get some text after to capture the full sentence if citation is mid-sentence
    end_pos = min(len(text), cite_start + 200)
    after_text = text[cite_start:end_pos]

    # Normalize whitespace
    before_text = re.sub(r'\s+', ' ', before_text)
    after_text = re.sub(r'\s+', ' ', after_text)

    # Legal abbreviations that end with periods but don't end sentences
    # These should NOT be treated as sentence boundaries
    legal_abbrevs = [
        r'v\.', r'vs\.', r'U\.S\.', r'S\.W\.', r'F\.', r'L\.Ed\.', r'S\.Ct\.',
        r'App\.', r'Cir\.', r'Dist\.', r'Ct\.', r'Crim\.', r'Tex\.', r'Cal\.',
        r'N\.Y\.', r'Ill\.', r'Fla\.', r'Ohio\.', r'Pa\.', r'Mass\.',
        r'No\.', r'Nos\.', r'Inc\.', r'Corp\.', r'Ltd\.', r'Co\.',
        r'Mr\.', r'Mrs\.', r'Ms\.', r'Dr\.', r'Jr\.', r'Sr\.', r'Prof\.',
        r'Id\.', r'See\.', r'Cf\.', r'E\.g\.', r'i\.e\.', r'e\.g\.',
        r'et al\.', r'op\.', r'pet\.', r'ref\'d\.', r'mem\.',
        r'[A-Z]\.',  # Single letter abbreviations like "J." for Justice
        r'\d+\.',  # Numbers followed by period (like "1." in lists)
    ]

    # Build pattern that matches sentence-ending punctuation
    # but NOT when preceded by common abbreviations
    # Strategy: find periods/!/? followed by space and capital letter,
    # then verify it's not an abbreviation

    # Find all potential sentence breaks
    potential_breaks = list(re.finditer(r'[.!?]\s+(?=[A-Z"\(])', before_text))

    # Filter out abbreviation false positives
    real_breaks = []
    for match in potential_breaks:
        pos = match.start()
        # Get text before this period
        preceding = before_text[max(0, pos-15):pos+1]

        # Check if this looks like an abbreviation
        is_abbrev = False
        for abbrev in legal_abbrevs:
            if re.search(abbrev + r'$', preceding, re.IGNORECASE):
                is_abbrev = True
                break

        # Also skip if previous char is a capital letter followed by period (initial)
        if re.search(r'\b[A-Z]\.$', preceding):
            is_abbrev = True

        if not is_abbrev:
            real_breaks.append(match)

    if real_breaks:
        # Get text from after the last real sentence break
        last_break = real_breaks[-1]
        sentence = before_text[last_break.end():].strip()
    else:
        # No clear sentence break found - might be first sentence or complex structure
        # Take a reasonable chunk
        sentence = before_text[-400:].strip()
        # Try to start at a capital letter after any leading fragment
        cap_match = re.search(r'(?:^|[.!?]\s+)([A-Z])', sentence)
        if cap_match and cap_match.start() > 0:
            sentence = sentence[cap_match.start():].lstrip('. ')

    # If sentence is very short, we may have over-filtered - expand
    if len(sentence) < 30 and potential_breaks:
        last_break = potential_breaks[-1]
        sentence = before_text[last_break.end():].strip()

    return sentence.strip()


def extract_case_name(text: str, citation_start: int) -> str:
    """Extract case name from text before citation."""
    before_text = text[max(0, citation_start - 200):citation_start]

    matches = list(re.finditer(
        r'([A-Z][a-zA-Z\'\-\.]+(?:\s+[A-Z][a-zA-Z\'\-\.]+)*)\s+v\.\s+([A-Z][a-zA-Z\'\-\.]+(?:\s+[A-Z][a-zA-Z\'\-\.]+)*)',
        before_text
    ))

    if matches:
        last_match = matches[-1]
        plaintiff = last_match.group(1).strip()
        defendant = last_match.group(2).strip()
        return f"{plaintiff} v. {defendant}"

    in_re_match = re.search(
        r'((?:In re|Ex parte)\s+[A-Z][a-zA-Z\'\-\.]+(?:\s+[A-Z][a-zA-Z\'\-\.]+)*)',
        before_text,
        re.IGNORECASE
    )
    if in_re_match:
        return in_re_match.group(1).strip()

    return "Unknown Case"


def extract_citations_from_argument(pdf_path: str, use_courtlistener: bool = True) -> list[CitationLink]:
    """Extract all citations from the argument section of a PDF."""
    text = extract_text_from_pdf(pdf_path)

    start_idx, end_idx = find_argument_boundaries(text)

    if start_idx is None:
        print("Warning: Could not find Argument section, searching entire document", file=sys.stderr)
        argument_text = text
    else:
        lines = text.split('\n')
        if end_idx is None:
            end_idx = len(lines)
        argument_text = '\n'.join(lines[start_idx:end_idx])

    # Extract citations using eyecite
    citations = get_citations(argument_text)

    results = []

    # Track positions for each citation occurrence
    search_start = 0

    for citation in citations:
        if not isinstance(citation, (FullCaseCitation, ShortCaseCitation)):
            continue

        volume = citation.groups.get('volume')
        reporter = citation.groups.get('reporter')
        page = citation.groups.get('page')

        if not all([volume, reporter, page]):
            continue

        # Get the matched text
        matched_text = citation.matched_text() if hasattr(citation, 'matched_text') else str(citation)

        # Find this specific occurrence
        cite_start = argument_text.find(matched_text, search_start)
        if cite_start == -1:
            cite_start = argument_text.find(matched_text)
        if cite_start == -1:
            continue

        cite_end = cite_start + len(matched_text)
        search_start = cite_end  # Next search starts after this one

        # Extract pinpoint
        after_cite = argument_text[cite_end:cite_end + 50]
        pinpoint = extract_pinpoint(after_cite, page)

        # Extract case name
        case_name = extract_case_name(argument_text, cite_start)

        # Extract year
        year = None
        year_match = re.search(r'\((\d{4})\)', argument_text[cite_start:cite_end + 100])
        if year_match:
            year = year_match.group(1)

        # Build full citation string
        full_citation = f"{volume} {reporter} {page}"
        if pinpoint:
            full_citation += f" at {pinpoint}"

        # Get preceding sentence
        preceding_sentence = get_preceding_sentence(argument_text, cite_start)

        # Look up on CourtListener
        cl_url = None
        if use_courtlistener:
            print(f"  Looking up: {volume} {reporter} {page}...", file=sys.stderr)
            cl_url = lookup_courtlistener(volume, reporter, page)
            time.sleep(1.0)  # Rate limiting - 1 second between requests

        # Build fallback Scholar URL
        scholar_url = build_scholar_url(volume, reporter, page, pinpoint)

        results.append(CitationLink(
            case_name=case_name,
            full_citation=full_citation,
            volume=volume,
            reporter=reporter,
            page=page,
            pinpoint=pinpoint,
            year=year,
            courtlistener_url=cl_url,
            scholar_url=scholar_url,
            preceding_sentence=preceding_sentence,
            position=cite_start
        ))

    return results


def generate_html_output(citations: list[CitationLink], pdf_name: str) -> str:
    """Generate an HTML page with clickable citation links."""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Citations from {html.escape(pdf_name)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #1a73e8;
            border-bottom: 2px solid #1a73e8;
            padding-bottom: 10px;
        }}
        .citation-card {{
            background: white;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }}
        .occurrence {{
            color: #5f6368;
            font-size: 0.8em;
            margin-bottom: 4px;
        }}
        .case-name {{
            font-weight: bold;
            font-size: 1.1em;
            color: #202124;
            margin-bottom: 8px;
        }}
        .citation {{
            font-family: 'Georgia', serif;
            color: #1a73e8;
            text-decoration: none;
            font-size: 1.05em;
        }}
        .citation:hover {{
            text-decoration: underline;
        }}
        .citation-link {{
            display: inline-block;
            margin-right: 12px;
        }}
        .fallback {{
            font-size: 0.85em;
            color: #666;
        }}
        .pinpoint {{
            background: #fff3cd;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
            margin-left: 8px;
        }}
        .preceding-sentence {{
            color: #202124;
            font-size: 0.95em;
            margin-top: 12px;
            padding: 10px 12px;
            background: #e8f0fe;
            border-left: 4px solid #1a73e8;
            border-radius: 0 4px 4px 0;
        }}
        .year {{
            color: #5f6368;
            font-size: 0.9em;
        }}
        .count {{
            color: #5f6368;
            margin-bottom: 20px;
        }}
        .no-cl {{
            color: #d93025;
            font-size: 0.85em;
        }}
        .source-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.75em;
            font-weight: 500;
            margin-left: 8px;
        }}
        .badge-cl {{
            background: #e6f4ea;
            color: #137333;
        }}
        .badge-scholar {{
            background: #fce8e6;
            color: #c5221f;
        }}
    </style>
</head>
<body>
    <h1>Citations from Argument Section</h1>
    <p class="count">Source: {html.escape(pdf_name)} | Found {len(citations)} citation references</p>
"""

    for i, cite in enumerate(citations, 1):
        pinpoint_html = f'<span class="pinpoint">at p. {html.escape(cite.pinpoint)}</span>' if cite.pinpoint else ''
        year_html = f' <span class="year">({html.escape(cite.year)})</span>' if cite.year else ''

        if cite.courtlistener_url:
            link_html = f'''<span class="citation-link">
                <a class="citation" href="{html.escape(cite.courtlistener_url)}" target="_blank">
                    {html.escape(cite.full_citation)}
                </a>
                <span class="source-badge badge-cl">CourtListener</span>
            </span>'''
        else:
            link_html = f'''<span class="citation-link">
                <a class="citation" href="{html.escape(cite.scholar_url)}" target="_blank">
                    {html.escape(cite.full_citation)}
                </a>
                <span class="source-badge badge-scholar">Google Scholar</span>
            </span>'''

        html_content += f"""
    <div class="citation-card">
        <div class="occurrence">Reference #{i}</div>
        <div class="case-name">{html.escape(cite.case_name)}{year_html}</div>
        {link_html}
        {pinpoint_html}
        <div class="preceding-sentence">{html.escape(cite.preceding_sentence)}</div>
    </div>
"""

    html_content += """
</body>
</html>
"""
    return html_content


def generate_text_output(citations: list[CitationLink]) -> str:
    """Generate plain text output with citations and links."""
    lines = []
    lines.append("=" * 70)
    lines.append("CITATIONS FROM ARGUMENT SECTION")
    lines.append("=" * 70)
    lines.append("")

    for i, cite in enumerate(citations, 1):
        lines.append(f"[{i}] {cite.case_name}")
        lines.append(f"    Citation: {cite.full_citation}")
        if cite.pinpoint:
            lines.append(f"    Pinpoint: page {cite.pinpoint}")
        if cite.year:
            lines.append(f"    Year: {cite.year}")
        if cite.courtlistener_url:
            lines.append(f"    CourtListener: {cite.courtlistener_url}")
        else:
            lines.append(f"    Google Scholar: {cite.scholar_url}")
        lines.append(f"    Context: \"{cite.preceding_sentence}\"")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"Total: {len(citations)} citation references")

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: argument_citations.py <pdf_file> [--html] [--output <file>] [--no-courtlistener]")
        print("\nOptions:")
        print("  --html             Output as HTML (default is plain text)")
        print("  --output <file>    Save output to file instead of stdout")
        print("  --no-courtlistener Skip CourtListener API lookups (faster, uses Google Scholar)")
        sys.exit(1)

    pdf_file = sys.argv[1]

    if not Path(pdf_file).exists():
        print(f"Error: File not found: {pdf_file}", file=sys.stderr)
        sys.exit(1)

    # Parse options
    output_html = '--html' in sys.argv
    use_courtlistener = '--no-courtlistener' not in sys.argv
    output_file = None
    if '--output' in sys.argv:
        output_idx = sys.argv.index('--output')
        if output_idx + 1 < len(sys.argv):
            output_file = sys.argv[output_idx + 1]

    print(f"Extracting citations from: {pdf_file}", file=sys.stderr)
    if use_courtlistener:
        print("Looking up cases on CourtListener...", file=sys.stderr)

    # Extract citations
    citations = extract_citations_from_argument(pdf_file, use_courtlistener=use_courtlistener)

    if not citations:
        print("No citations found in argument section.", file=sys.stderr)
        sys.exit(0)

    print(f"\nFound {len(citations)} citation references", file=sys.stderr)

    # Generate output
    pdf_name = Path(pdf_file).name
    if output_html:
        output = generate_html_output(citations, pdf_name)
        default_ext = '.html'
    else:
        output = generate_text_output(citations)
        default_ext = '.txt'

    # Write or print output
    if output_file:
        with open(output_file, 'w') as f:
            f.write(output)
        print(f"Output saved to: {output_file}", file=sys.stderr)
    else:
        if output_html:
            # Save next to the source PDF
            pdf_path = Path(pdf_file)
            output_file = pdf_path.parent / (pdf_path.stem + '_citations.html')
            with open(output_file, 'w') as f:
                f.write(output)
            print(f"HTML output saved to: {output_file}", file=sys.stderr)
        else:
            print(output)


if __name__ == "__main__":
    main()
