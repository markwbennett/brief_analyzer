#!/usr/bin/env python
import os
import json
import sys
import argparse
from datetime import datetime
import markdown
import weasyprint  # For PDF generation
import re

def load_opinion_data(file_path):
    """Load opinion data from a JSON file"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return None

def fix_courtlistener_links(html_content):
    """Fix internal links to point to CourtListener website"""
    # Pattern for links starting with /opinion/
    pattern = r'(href=")(/opinion/[^"]+)(")'
    replacement = r'\1https://www.courtlistener.com\2\3'
    
    # Replace all occurrences
    fixed_html = re.sub(pattern, replacement, html_content)
    
    return fixed_html

def format_html(data):
    """Format opinion data as HTML"""
    # Use the HTML with citations if available, or generate our own otherwise
    if data.get('html_with_citations'):
        content = data['html_with_citations']
    elif data.get('html_lawbox'):
        content = data['html_lawbox']
    elif data.get('html_columbia'):
        content = data['html_columbia']
    elif data.get('plain_text'):
        # Convert plain text to HTML
        content = f"<pre>{data['plain_text']}</pre>"
    else:
        # Generate basic HTML from available fields
        case_name = data.get('case_name_full') or data.get('case_name') or "Unknown Case"
        court = "Supreme Court of Texas"
        date = data.get('date_filed') or ""
        
        content = f"""
        <div style="max-width: 800px; margin: 0 auto; font-family: Georgia, serif;">
            <h1 style="text-align: center;">{case_name}</h1>
            <p style="text-align: center;"><strong>{court}</strong></p>
            <p style="text-align: center;">{date}</p>
            <hr>
            
            <div style="line-height: 1.6; margin-top: 2em;">
                {data.get('html', '<p>No opinion text available</p>')}
            </div>
        </div>
        """
    
    # Fix internal CourtListener links
    content = fix_courtlistener_links(content)
    
    # Wrap in full HTML document
    html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{data.get('case_name', 'Legal Opinion')}</title>
    <style>
        body {{
            font-family: Georgia, serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #fff;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{
            font-family: "Times New Roman", Times, serif;
        }}
        h1 {{
            text-align: center;
            font-size: 24px;
            margin-bottom: 5px;
        }}
        .court, .date {{
            text-align: center;
            margin-top: 5px;
            margin-bottom: 5px;
        }}
        .citation {{
            text-align: center;
            font-weight: bold;
            margin-bottom: 20px;
        }}
        p {{
            text-indent: 2em;
            margin-top: 0.6em;
            margin-bottom: 0.6em;
        }}
        .judges {{
            margin-top: 20px;
            font-style: italic;
        }}
        .star-pagination {{
            color: #777;
            padding: 0 5px;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""
    
    return html_doc

def format_txt(data):
    """Format opinion data as plain text"""
    if data.get('plain_text'):
        return data['plain_text']
    
    # Generate text from available fields if plain_text not available
    case_name = data.get('case_name_full') or data.get('case_name') or "Unknown Case"
    citation = data.get('citation') or ""
    court = "Supreme Court of Texas"
    date = data.get('date_filed') or ""
    judges = data.get('judges') or ""
    
    # Try to get text from HTML fields by stripping HTML tags (rough approach)
    content = ""
    
    if data.get('html_lawbox'):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(data['html_lawbox'], 'html.parser')
        content = soup.get_text('\n')
    elif data.get('html_columbia'):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(data['html_columbia'], 'html.parser')
        content = soup.get_text('\n')
    elif data.get('html'):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(data['html'], 'html.parser')
        content = soup.get_text('\n')
    else:
        content = "No opinion text available."
    
    # Construct text document with proper formatting
    txt_doc = f"""{case_name}
{citation}
{court}
{date}
{judges}

{content}
"""
    
    return txt_doc

def format_md(data):
    """Format opinion data as Markdown"""
    case_name = data.get('case_name_full') or data.get('case_name') or "Unknown Case"
    citation = data.get('citation') or ""
    court = "Supreme Court of Texas"
    date = data.get('date_filed') or ""
    judges = data.get('judges') or ""
    
    # Try to get content from available fields
    content = ""
    
    if data.get('plain_text'):
        content = data['plain_text']
    elif data.get('html_lawbox') or data.get('html_columbia') or data.get('html'):
        from bs4 import BeautifulSoup
        html_content = data.get('html_lawbox') or data.get('html_columbia') or data.get('html')
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Get all links first to properly convert them in the markdown
        links = {}
        for a in soup.find_all('a'):
            if a.get('href') and a.get('href').startswith('/opinion/'):
                href = a.get('href')
                full_url = f"https://www.courtlistener.com{href}"
                links[href] = full_url
        
        # Convert some basic HTML to Markdown
        paragraphs = soup.find_all('p')
        for p in paragraphs:
            p_text = p.get_text().strip()
            if p_text:
                content += p_text + "\n\n"
        
        # Add a list of links at the end for references
        if links:
            content += "\n## References\n\n"
            for href, url in links.items():
                case_id = href.split('/')[2]
                content += f"* Case #{case_id}: [{url}]({url})\n"
    else:
        content = "No opinion text available."
    
    # Add a link to the original opinion on CourtListener if available
    if data.get('id'):
        opinion_url = f"https://www.courtlistener.com/opinion/{data['id']}/"
        content += f"\n\n---\n\nView this opinion on CourtListener: [{opinion_url}]({opinion_url})"
    
    # Construct Markdown document
    md_doc = f"""# {case_name}

**{citation}**

## {court}

*{date}*

**Judges:** {judges}

---

{content}
"""
    
    return md_doc

def save_formats(data, base_filename):
    """Save opinion data in multiple formats"""
    # Create HTML
    html_content = format_html(data)
    html_file = f"{base_filename}.html"
    with open(html_file, 'w') as f:
        f.write(html_content)
    print(f"Saved HTML to {html_file}")
    
    # Create TXT
    txt_content = format_txt(data)
    txt_file = f"{base_filename}.txt"
    with open(txt_file, 'w') as f:
        f.write(txt_content)
    print(f"Saved TXT to {txt_file}")
    
    # Create MD
    md_content = format_md(data)
    md_file = f"{base_filename}.md"
    with open(md_file, 'w') as f:
        f.write(md_content)
    print(f"Saved Markdown to {md_file}")
    
    # Create PDF from HTML
    pdf_file = f"{base_filename}.pdf"
    try:
        weasyprint.HTML(string=html_content).write_pdf(pdf_file)
        print(f"Saved PDF to {pdf_file}")
    except Exception as e:
        print(f"Error creating PDF: {e}")
        print("PDF generation requires WeasyPrint. Install with: pip install weasyprint")

def main():
    parser = argparse.ArgumentParser(description="Format legal opinion data into multiple file formats")
    parser.add_argument("json_file", help="Path to the opinion JSON file")
    parser.add_argument("--output", "-o", help="Base name for output files (default: based on citation)")
    parser.add_argument("--citation", "-c", help="Original citation used for the lookup (for filename)")
    
    args = parser.parse_args()
    
    # Load the opinion data
    data = load_opinion_data(args.json_file)
    if not data:
        return 1
    
    # Get the directory of the input file
    input_dir = os.path.dirname(args.json_file)
    if input_dir == '':
        input_dir = '.'
    
    # Determine base filename
    if args.output:
        base_filename = args.output
    elif args.citation:
        # Use the original citation provided by the user
        clean_citation = args.citation.replace(' ', '_').replace('.', '')
        base_filename = os.path.join(input_dir, f"citation_{clean_citation}")
    else:
        # Try to extract citation from the data
        citation = data.get('citation', '')
        if citation:
            clean_citation = citation.replace(' ', '_').replace('.', '')
            base_filename = os.path.join(input_dir, f"citation_{clean_citation}")
        else:
            # Fall back to case name or ID
            case_name = data.get('case_name', '').replace(' ', '_').replace(',', '').lower()
            opinion_id = data.get('id', '')
            
            if case_name:
                base_filename = os.path.join(input_dir, f"{case_name}_{opinion_id}")
            else:
                base_filename = os.path.join(input_dir, f"opinion_{opinion_id}")
    
    # Save in all formats
    save_formats(data, base_filename)
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 