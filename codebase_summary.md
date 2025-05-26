# Brief Analyzer Codebase Summary

## Core Components

### Citation Extraction
- **extract_authorities.py**: Extracts case citations from PDF briefs, identifies the Table of Authorities and Argument sections, and saves the extracted information to a database.
- **eyecite_extractor.py**: General-purpose citation extractor that uses the eyecite library to find and parse legal citations from various document formats.
- **extract_minimal.py**: Minimal version of citation extraction that only extracts volume, reporter, and page information.
- **extract_text.py**: Simple utility to extract text from PDF files and save raw and cleaned versions.

### Citation Lookup and Enrichment
- **citation_lookup.py**: Performs citation lookups against the CourtListener API.
- **citation_lookup_test.py**: Interactive tool to test citation lookups with detailed output.
- **citation_info.py**: Command-line tool to retrieve and display citation information.
- **citations_enricher.py**: Enriches citation data from CSV files with additional metadata from CourtListener.

### API Interaction
- **courtlistener_api.py**: Complete API client for CourtListener with various functions (search, citation lookup, opinion retrieval).
- **fetch_opinion.py**: Interactive tool to fetch and save case opinions by citation or ID.
- **get_opinion_text.py**: Retrieves full text of opinions from CourtListener by citation.

### Data Processing and Formatting
- **format_opinion.py**: Converts opinion data to various formats (HTML, PDF, TXT, Markdown).
- **generate_report.py**: Creates reports from citation data in different formats.
- **citations_db.py**: Provides database functionality for storing and retrieving citation data.

### Utilities
- **legal_abbreviations.py**: Handles expansion of legal abbreviations to improve citation recognition.
- **debug_toa.py**: Helps with debugging Table of Authorities extraction issues.

### Tests
- **test_citation.py**: Tests for citation parsing functionality.
- **test_extraction.py**: Tests for text extraction functionality.
- **test_eyecite_fields.py**: Tests for eyecite field extraction.
- **test_party_extraction.py**: Tests for party name extraction from citations.
- **test_party_name_logic.py**: Tests for logic used in party name processing.

## Workflows

### 1. Extract Citations from Brief
```
PDF Brief → extract_authorities.py → citation database and text files
```
- Extracts raw text from PDF
- Identifies Table of Authorities section
- Cleans and processes text
- Extracts citations and metadata
- Stores in SQLite database

### 2. Lookup Citations
```
Citation → citation_lookup.py/courtlistener_api.py → Citation metadata
```
- Takes citation (volume, reporter, page)
- Queries CourtListener API
- Returns metadata about the case

### 3. Generate Reports
```
Citations database → generate_report.py → Formatted report (text/CSV)
```
- Reads citation data from database
- Groups by reporter 
- Creates formatted reports

### 4. Fetch and Format Opinions
```
Citation → fetch_opinion.py → JSON data → format_opinion.py → HTML/PDF/Markdown/Text formats
```
- Fetches full opinion data
- Formats in multiple output formats
- Saves to files

### 5. Enrich Citation Data
```
CSV with citations → citations_enricher.py → Enriched CSV with metadata
```
- Reads citation data from CSV
- Looks up each citation via CourtListener
- Adds metadata to citation records
- Optionally saves full opinion text 