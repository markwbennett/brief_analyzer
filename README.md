# Legal Citation Extractor

A Python script for extracting legal citations from documents using the [eyecite](https://github.com/freelawproject/eyecite) library.

## Features

- Extracts case citations (e.g., Brown v. Board of Education, 347 U.S. 483 (1954))
- Extracts statutory citations (e.g., 42 U.S.C. § 1983)
- Extracts constitutional citations
- Provides detailed information about each citation including:
  - Case names (plaintiff and defendant)
  - Reporter information
  - Year
  - Court
  - Volume and page numbers
- Outputs citations in structured JSON format

## Requirements

- Python 3.6+
- eyecite library

## Installation

```bash
# With pipenv (recommended)
pipenv install eyecite

# Or with pip
pip install eyecite
```

## Usage

```bash
# Basic usage
pipenv run python eyecite_extractor.py document.txt

# Process multiple files
pipenv run python eyecite_extractor.py document1.txt document2.txt document3.txt

# Output in JSON format
pipenv run python eyecite_extractor.py document.txt --json

# Save results to a file
pipenv run python eyecite_extractor.py document.txt --output results.json

# Show debug information
pipenv run python eyecite_extractor.py document.txt --debug
```

## Citation Types Detected

The script can detect and extract various citation types, including:

- **FullCaseCitation**: Complete case citations with volume, reporter, and page number
- **FullLawCitation**: Statutory citations
- **ConstitutionalCitation**: Citations to constitutional provisions

## Output Format

When using the `--json` flag, the script outputs an array of citation objects with the following structure:

```json
{
  "type": "FullCaseCitation|FullLawCitation|...",
  "text": "Full citation text",
  "context": "Surrounding text",
  "year": "1954",
  "plaintiff": "Brown",
  "defendant": "Board of Education",
  "volume": "347",
  "reporter": "U.S.",
  "page": "483",
  "court": "scotus",
  "groups": {},
  "file": "Source file"
}
```

## Credits

This tool uses the [eyecite](https://github.com/freelawproject/eyecite) library developed by the Free Law Project.

## CourtListener API Client

This repository includes a simple command line client for the CourtListener API. The client allows you to search for opinions, look up cases by citation, and retrieve information about dockets.

### Setup

Before using the API client, you need to:

1. Register for an account at [CourtListener](https://www.courtlistener.com/)
2. Get an API token from your profile page at [https://www.courtlistener.com/profile/api/](https://www.courtlistener.com/profile/api/)
3. Set your API token as an environment variable:

```bash
export COURT_LISTENER_TOKEN="your_api_token_here"
```

Alternatively, you can create a `.env` file in the project root with:

```
COURT_LISTENER_TOKEN=your_api_token_here
```

### Usage

```bash
# Get help and see all options
./courtlistener_api.py -h

# List available API endpoints
./courtlistener_api.py endpoints

# Search for opinions
./courtlistener_api.py search "fourth amendment"

# Search with pagination 
./courtlistener_api.py search "fourth amendment" --page 2

# Get all search results (limited to 10 pages by default)
./courtlistener_api.py search "fourth amendment" --all

# Get all search results with a custom page limit
./courtlistener_api.py search "fourth amendment" --all --max-pages 5

# Save search results to a file
./courtlistener_api.py search "fourth amendment" --output results.json

# Look up a case by citation
./courtlistener_api.py citation "410 U.S. 113"

# Get details for a specific opinion and save to file
./courtlistener_api.py opinion 12345 --output opinion.json

# Get details for a specific docket
./courtlistener_api.py docket 67890

# Get the full text of an opinion by citation
./courtlistener_api.py text "410 U.S. 113" --metadata

# Save the opinion text to a file
./courtlistener_api.py text "410 U.S. 113" --output roe_v_wade.txt

# Use direct citation format (more reliable for some citations)
./courtlistener_api.py direct "U.S." "410" "113"

# Save direct citation lookup results to a file
./courtlistener_api.py direct "U.S." "347" "483" --output brown_v_board.json
```

### API Documentation

For full API documentation, see the [CourtListener API documentation](https://www.courtlistener.com/help/api/).

### Working with State Court Citations

The CourtListener API may return a "400 Bad Request" error for some state court citations. This often happens because state reporter citations need to specify the state. The `--try-alternatives` flag helps with this by:

1. Trying various format variations (with/without periods, different spacing)
2. Automatically adding appropriate state abbreviations for common reporters:
   - For S.W./S.W.2d/S.W.3d: Tex., Ky., Mo., Tenn., Ark.
   - For P./P.2d/P.3d: Cal., Colo., Kan., Or., Wash.
   - For N.E.: Ill., Ind., Mass., N.Y., Ohio
   - For N.W.: Iowa, Mich., Minn., Neb., Wis.
   - And more...

Examples of properly formatted state citations:
- `698 S.W.2d 362 (Tex.)` instead of just `698 S.W.2d 362`
- `543 N.E.2d 49 (Ill.)` instead of just `543 N.E.2d 49`

### Direct Citation Format

For more reliable citation lookup, especially for federal cases, you can use the direct citation format:

```bash
./courtlistener_api.py direct REPORTER VOLUME PAGE
```

This uses CourtListener's URL citation format (e.g., `/c/U.S./410/113/` for Roe v. Wade). This format is:
- More reliable for federal cases
- Doesn't require authentication 
- Works with standard reporter abbreviations
- Bypasses the API's citation validation

#### Common Reporter Abbreviations:
- `U.S.` - United States Reports (Supreme Court)
- `F.` - Federal Reporter
- `F.2d` - Federal Reporter, Second Series
- `F.3d` - Federal Reporter, Third Series
- `S.Ct.` - Supreme Court Reporter
- `L.Ed.` - Lawyers' Edition Supreme Court Reports
- `L.Ed.2d` - Lawyers' Edition Supreme Court Reports, Second Series

The `--debug` flag will show which citation formats are being tried.

## Test Scripts

The repository includes two test scripts for interacting with the CourtListener API:

### Interactive Test Script

The `citation_lookup_test.py` script is an interactive tool that prompts for a citation and retrieves all available information:

```bash
# Run the interactive test script
./citation_lookup_test.py
```

The script will:
1. Ask if you want to enter an API token (if not set in the environment)
2. Prompt for a citation to look up
3. Retrieve all available information from CourtListener
4. Save the results to a text file with a timestamp

### Command-Line Test Script

The `citation_info.py` script is a non-interactive command-line tool with more options:

```bash
# Basic usage
./citation_info.py "410 U.S. 113"

# Include opinion text
./citation_info.py "410 U.S. 113" --include-text

# Save to a specific file
./citation_info.py "410 U.S. 113" --output roe_v_wade.txt

# Use a specific API token
./citation_info.py "410 U.S. 113" --token YOUR_API_TOKEN

# Output in JSON format
./citation_info.py "410 U.S. 113" --format json

# Try alternative citation formats if lookup fails
./citation_info.py "698 S.W.2d 362" --try-alternatives

# Show debug information
./citation_info.py "698 S.W.2d 362" --debug --try-alternatives
```

Both scripts provide detailed error messages if the lookup fails, including instructions on how to get an API token.

## Citations Enricher

The Citations Enricher tool uses the CourtListener API to add metadata to citations extracted from legal briefs.
It takes a CSV file with citation data, looks up each citation in the CourtListener database, and adds additional
information such as case name, court, date filed, and URLs.

### Usage

```bash
# Enrich a citations CSV file with CourtListener data
./citations_enricher.py citations_report.csv enriched_citations.csv

# Specify a custom API token
./citations_enricher.py citations_report.csv enriched_citations.csv --token YOUR_API_TOKEN

# Specify a custom log file for failed lookups
./citations_enricher.py citations_report.csv enriched_citations.csv --log my_errors.log

# Specify custom column names if your CSV has different headers
./citations_enricher.py citations_report.csv enriched_citations.csv --citation-column "Citation" --case-column "Case Title"

# Include opinion text and save to the default directory (opinion_texts/)
./citations_enricher.py citations_report.csv enriched_citations.csv --include-text

# Include opinion text and save to a custom directory
./citations_enricher.py citations_report.csv enriched_citations.csv --include-text --text-dir my_opinions
```

### Input Format

By default, the script looks for:
- A "Citation" column containing the citation to look up (e.g., "410 U.S. 113")
- A "Case Title" column with the case name (e.g., "Roe v. Wade")

The script will:
- Skip citations that start with "No." (case numbers rather than formal citations)
- Format citations with case names when appropriate

### Output Format

The output CSV file will contain all the original columns plus additional columns with the CourtListener data:

- `cl_opinion_id` - The opinion ID in CourtListener
- `cl_case_name` - The case name
- `cl_court` - The court that issued the opinion
- `cl_date_filed` - The date the opinion was filed
- `cl_absolute_url` - The URL to view the opinion on CourtListener
- `cl_other_citations` - Other citation forms for this case

If `--include-text` is specified, these additional columns will be included:
- `cl_text_file` - Path to the file containing the full opinion text
- `cl_text_preview` - A preview of the opinion text (first 300 characters) 