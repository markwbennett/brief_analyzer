# Detailed Component Analysis

## Citation Extraction Tools

### extract_authorities.py
- **Primary Purpose**: Extract citations from legal briefs' Table of Authorities
- **Key Functions**:
  - `clean_text()`: Removes page numbers and normalizes formatting
  - `find_toa_boundaries()`: Locates Table of Authorities section in document
  - `find_argument_boundaries()`: Locates Argument section in document
  - `find_citations()`: Uses eyecite to extract citations and store in database
- **Input**: PDF legal brief
- **Output**: 
  - Text files with extracted content
  - Citations stored in SQLite database
- **Dependencies**: eyecite, pdfminer.six, sqlite3

### eyecite_extractor.py
- **Primary Purpose**: General-purpose legal citation extraction
- **Key Functions**:
  - `extract_text_from_pdf()`: Extract text from PDF files
  - `extract_text_from_docx()`: Extract text from DOCX files
  - `extract_case_citations()`: Parse and extract citations
  - `process_file()`: Process files in various formats
  - `generate_html_output()`: Create HTML with citation links
- **Input**: Text, PDF, or DOCX documents
- **Output**: Structured citation data or HTML with linked citations
- **Dependencies**: eyecite, pdfminer.six, beautifulsoup4

### extract_text.py
- **Primary Purpose**: Simple text extraction from PDFs
- **Key Functions**:
  - `extract_text()`: Extract and save both raw and normalized text
- **Input**: PDF file
- **Output**: Two text files - raw extracted text and cleaned text
- **Dependencies**: eyecite_extractor module

### extract_minimal.py
- **Primary Purpose**: Minimal citation extraction example
- **Key Functions**:
  - `extract_minimal_citation_data()`: Extract basic citation components
- **Input**: Text with citations
- **Output**: List of citation dictionaries with volume, reporter, and page
- **Dependencies**: eyecite

## Citation Lookup and Enrichment

### courtlistener_api.py
- **Primary Purpose**: Comprehensive CourtListener API client
- **Key Functions**:
  - `search()`: Search for opinions
  - `get_opinion()`: Get opinion by ID
  - `get_docket()`: Get docket by ID
  - `citation_lookup()`: Look up cases by citation
  - `get_text_by_citation()`: Get full text by citation
  - `direct_citation_lookup()`: Look up using direct citation format
- **Input**: Search terms, citation strings, or IDs
- **Output**: JSON data from API or formatted text
- **Dependencies**: requests, dotenv

### citation_lookup.py
- **Primary Purpose**: Simple citation lookup utility
- **Key Functions**:
  - `lookup_citation()`: Look up citation via CourtListener
  - `save_to_file()`: Save API response to file
- **Input**: Volume, reporter, page
- **Output**: JSON response saved to file
- **Dependencies**: requests, json

### citation_lookup_test.py
- **Primary Purpose**: Interactive testing tool
- **Key Functions**:
  - Interactive prompts for citation lookup
  - Comprehensive results display
- **Input**: User-provided citation
- **Output**: Formatted text file with citation details
- **Dependencies**: courtlistener_api, json

### citations_enricher.py
- **Primary Purpose**: Enrich citation data from CSV
- **Key Functions**:
  - `read_citations()`: Read citation data from CSV
  - `enrich_citation()`: Add metadata from CourtListener
  - `write_enriched_citations()`: Save enriched data to CSV
- **Input**: CSV file with citation data
- **Output**: Enriched CSV with additional metadata
- **Dependencies**: courtlistener_api, csv, json

## Data Processing and Formatting

### format_opinion.py
- **Primary Purpose**: Convert opinion data to multiple formats
- **Key Functions**:
  - `format_html()`: Format as HTML
  - `format_txt()`: Format as plain text
  - `format_md()`: Format as Markdown
  - `save_formats()`: Save in all formats
- **Input**: JSON opinion data
- **Output**: HTML, TXT, MD, and PDF files
- **Dependencies**: weasyprint, markdown, beautifulsoup4

### generate_report.py
- **Primary Purpose**: Generate reports from citation database
- **Key Functions**:
  - `get_citation_data()`: Extract citation data from database
  - `group_by_reporter()`: Organize citations by reporter
  - `generate_report()`: Create formatted report
- **Input**: SQLite database
- **Output**: Text or CSV report
- **Dependencies**: sqlite3, tabulate

### citations_db.py
- **Primary Purpose**: Database operations for citations
- **Key Functions**:
  - `CitationDB` class: Database interface
  - `ExtendedCitation` class: Enhanced citation object
- **Input**: Citation data
- **Output**: Database records
- **Dependencies**: sqlite3

## Data Flow and Interactions

1. **PDF Ingestion Pipeline**:
   - `extract_text.py` → Extract raw text
   - `extract_authorities.py` → Find Table of Authorities
   - `find_citations()` → Extract and store citations

2. **Citation Enrichment Pipeline**:
   - `citations_enricher.py` → Read CSV citations
   - `courtlistener_api.py` → Look up metadata
   - Output enriched CSV

3. **Opinion Retrieval and Formatting**:
   - `fetch_opinion.py` → Interactive opinion retrieval
   - `get_opinion_text.py` → Get full opinion text
   - `format_opinion.py` → Convert to multiple formats

4. **Reporting Pipeline**:
   - `citations_db.py` → Query citation database
   - `generate_report.py` → Create formatted reports 