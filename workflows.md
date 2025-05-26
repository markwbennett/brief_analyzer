# Key Workflows in Brief Analyzer

## 1. Citation Extraction from Legal Briefs

The primary workflow in the Brief Analyzer codebase is extracting citations from legal briefs, particularly from the Table of Authorities section.

### Step-by-Step Process:
1. **Text Extraction**: `extract_authorities.py` uses `pdfminer.six` to extract raw text from the PDF brief
2. **Section Detection**: The script identifies the Table of Authorities (TOA) section using pattern matching and structural analysis
3. **Text Cleaning**: The raw TOA text is cleaned to remove page numbers and normalize formatting
4. **Citation Extraction**: The `eyecite` library identifies legal citations in the text
5. **Data Enrichment**: Additional metadata is extracted (case title, court, year, etc.)
6. **Database Storage**: Citations are stored in a SQLite database for further analysis
7. **Output Generation**: Various text files are created (raw text, cleaned TOA, argument section, etc.)

```
Input: brief.pdf
↓
extract_authorities.py
↓
Output: 
- brief_debug_raw.txt (raw text)
- brief.txt (full text)
- brief_toa_raw.txt (raw Table of Authorities)
- brief_toa_cleaned.txt (cleaned Table of Authorities)
- brief_argument.txt (argument section)
- brief_citations_db.txt (formatted citations)
- citations.db (SQLite database)
```

## 2. Citation Lookup via CourtListener API

This workflow allows users to look up legal citations to get comprehensive case information.

### Step-by-Step Process:
1. **Citation Input**: User provides a legal citation (e.g., "410 U.S. 113")
2. **API Query**: The citation is formatted and sent to the CourtListener API
3. **Response Processing**: The API response is parsed to extract relevant information
4. **Display/Storage**: Results are displayed to the user and/or saved to a file

This functionality is provided through multiple interfaces:
- `citation_lookup.py`: Simple command-line interface
- `citation_lookup_test.py`: Interactive interface with comprehensive output
- `citation_info.py`: Advanced command-line tool with multiple options
- `courtlistener_api.py`: Direct API client with multiple endpoints

```
Input: "410 U.S. 113"
↓
courtlistener_api.py (citation_lookup method)
↓
Output:
- JSON response with case metadata
- Formatted text output (optional)
- Saved output file (optional)
```

## 3. Opinion Retrieval and Formatting

This workflow retrieves full legal opinions and formats them in various ways.

### Step-by-Step Process:
1. **Citation Input**: User provides a legal citation or opinion ID
2. **API Query**: The citation is used to query the CourtListener API
3. **Text Retrieval**: The full opinion text is retrieved
4. **Format Conversion**: The opinion is formatted in multiple formats
5. **Storage**: Formatted opinions are saved to files

This functionality is provided through:
- `fetch_opinion.py`: Interactive tool to fetch and save opinions
- `get_opinion_text.py`: Library to retrieve opinion text by citation
- `format_opinion.py`: Converts opinions to various formats

```
Input: "410 U.S. 113" or opinion ID
↓
fetch_opinion.py → get_opinion_by_citation() or get_opinion_by_id()
↓
format_opinion.py
↓
Output:
- opinion_xxx.html (HTML format)
- opinion_xxx.txt (plain text)
- opinion_xxx.md (Markdown)
- opinion_xxx.pdf (PDF)
```

## 4. Citation Data Enrichment

This workflow takes a CSV file containing citation data and enriches it with metadata from the CourtListener API.

### Step-by-Step Process:
1. **CSV Input**: User provides a CSV file with citation data
2. **CSV Parsing**: Citations are extracted from the CSV
3. **API Lookup**: Each citation is looked up via the CourtListener API
4. **Data Enrichment**: Additional metadata is added to each citation record
5. **CSV Output**: Enriched data is saved to a new CSV file

```
Input: citations.csv
↓
citations_enricher.py
↓
Output:
- enriched_citations.csv (with additional metadata)
- opinion_texts/ (optional directory with full opinion texts)
- lookup_errors.log (record of failed lookups)
```

## 5. Report Generation

This workflow generates formatted reports from citation data in the database.

### Step-by-Step Process:
1. **Database Query**: Citation data is retrieved from the SQLite database
2. **Data Organization**: Citations are grouped by reporter
3. **Formatting**: Data is formatted as text or CSV
4. **Output**: Formatted report is displayed or saved to a file

```
Input: citations.db
↓
generate_report.py
↓
Output:
- Text report (console output or saved file)
- CSV report (saved file)
```

## Utility Workflows

### Expanding Legal Abbreviations
`legal_abbreviations.py` provides functionality to expand common legal abbreviations, which improves citation recognition.

### Citation Database Management
`citations_db.py` provides an interface for storing and retrieving citation data in a structured way. 