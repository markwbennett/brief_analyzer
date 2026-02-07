# Brief Analyzer

Automated pipeline for analyzing Texas appellate briefs. Downloads filings from txcourts.gov, extracts cited authorities, downloads case opinions from CourtListener and Westlaw, cite-checks every citation, generates issue analysis and moot court Q&A, and produces PDF reports.

## Pipeline Steps

| # | Step | Description |
|---|------|-------------|
| 1 | `fetch` | Download filings from txcourts.gov |
| 2 | `convert` | Convert PDFs to text (`pdftotext`) |
| 3 | `authorities` | Extract authorities list (Claude) |
| 4 | `courtlistener` | Download cases from CourtListener API (free) |
| 5 | `westlaw` | Download remaining cases from Westlaw (semi-automated) |
| 6 | `process` | Convert RTFs to text, rename with full citations |
| 7 | `verify` | Verify all authorities are downloaded |
| 8 | `citecheck` | Parallel cite-check of all briefs (Claude) |
| 9 | `analysis` | Generate issue analysis (Claude) |
| 10 | `mootqa` | Generate moot court Q&A (Claude) |
| 11 | `pdf` | Generate PDF outputs (pandoc) |

Steps 4 and 5 work together: CourtListener is tried first (free, no login), and the Westlaw step automatically skips any citations already downloaded. If CourtListener covers everything, Westlaw is skipped entirely.

## Requirements

- Python 3.12+
- [pdftotext](https://poppler.freedesktop.org/) (from poppler) -- for PDF conversion
- [pandoc](https://pandoc.org/) + LaTeX -- for PDF generation
- [Claude Code](https://claude.ai/claude-code) -- for AI-powered steps (authorities, citecheck, analysis, mootqa)
- [Playwright](https://playwright.dev/python/) -- for Westlaw automation (only if needed)

## Installation

```bash
git clone git@github.com:markwbennett/brief_analyzer.git
cd brief-analyzer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install Playwright browser (only needed for Westlaw step)
python -m playwright install chromium
```

## Configuration

### CourtListener API Token

Get a free token at https://www.courtlistener.com/sign-in/ and set it as an environment variable:

```bash
export COURTLISTENER_TOKEN=your_token_here
```

Or add it to `brief_config.yaml`:

```yaml
courtlistener:
  api_token: your_token_here
```

### Config File

Copy `brief_config.yaml` to your project directory and customize:

```yaml
courtlistener:
  # api_token: your_token_here  # or use COURTLISTENER_TOKEN env var

westlaw:
  login_url: https://next.westlaw.com

pandoc:
  font: Equity B
  font_size: 14
  heading_font: Concourse 6
  margins: 1.5in

claude_model: opus
parallel_agents: 4
```

## Usage

### Full Pipeline

```bash
# Fetch filings and run everything
python -m brief_analyzer /path/to/project --case 01-24-00686-CR

# Run on a directory that already has PDFs
python -m brief_analyzer /path/to/project
```

### Single Step

```bash
python -m brief_analyzer /path/to/project --step courtlistener
python -m brief_analyzer /path/to/project --step citecheck
```

### Resume from Last Failure

```bash
python -m brief_analyzer /path/to/project --resume
```

### Check Status

```bash
python -m brief_analyzer /path/to/project --status
```

### CLI Options

```
positional arguments:
  project_dir          Path to the project directory

options:
  --case CASE_NUMBER   Case number (e.g., 01-24-00686-CR)
  --coa COA            Court of appeals code (e.g., coa01)
  --step STEP          Run a single pipeline step
  --resume             Resume from the first incomplete step
  --parallel N         Number of parallel Claude agents (default: 4)
  --model MODEL        Claude model (default: opus)
  --config PATH        Path to brief_config.yaml
  --status             Show pipeline status and exit
```

## Output Files

The pipeline generates these files in the project directory:

| File | Description |
|------|-------------|
| `AUTHORITIES.md` | Master authority list with citations and propositions |
| `COURTLISTENER_RESULTS.json` | CourtListener download results (found/not_found) |
| `CITECHECK.md` / `.pdf` | Cite-check report for all briefs |
| `ISSUE_ANALYSIS.md` / `.pdf` | Deep issue analysis |
| `MOOT_QA.md` / `.pdf` | Moot court Q&A preparation |
| `authorities/*.txt` | Downloaded case opinion texts |
| `authorities/rtf/*.rtf` | Westlaw RTF originals |
| `.pipeline_state.json` | Pipeline state (for resume) |

## Project Structure

```
brief_analyzer/
  __init__.py
  __main__.py          # Entry point
  cli.py               # Argument parsing
  config.py            # Configuration dataclasses + YAML loading
  pipeline.py          # Step orchestration
  state.py             # Pipeline state persistence
  steps/
    s0_fetch_case.py          # txcourts.gov downloader
    s1_convert_pdfs.py        # PDF to text
    s2_extract_authorities.py # Claude-powered authority extraction
    s2b_courtlistener.py      # CourtListener API downloads
    s3_westlaw_download.py    # Semi-automated Westlaw downloads
    s4_process_authorities.py # RTF conversion and renaming
    s5_verify_authorities.py  # Authority file verification
    s5_citecheck.py           # Parallel cite-checking
    s6_issue_analysis.py      # Issue analysis generation
    s7_moot_qa.py             # Moot court Q&A generation
    s8_generate_pdfs.py       # PDF generation via pandoc
  prompts/
    authority_extraction.py   # Prompt for authority extraction
    citecheck.py              # Prompt for cite-checking
    issue_analysis.py         # Prompt for issue analysis
    moot_qa.py                # Prompt for moot Q&A
  utils/
    citation_parser.py        # Citation regex extraction
    claude_runner.py          # Claude API wrapper
    file_utils.py             # Filename sanitization, file finding
    pdf_utils.py              # PDF generation helpers
```

## CourtListener Coverage

CourtListener provides free access to opinions from:
- U.S. Supreme Court (U.S. Reports)
- Federal circuit courts (F.2d, F.3d, F.4th)
- Federal district courts (F. Supp., F. Supp. 2d)
- Texas state courts (S.W.2d, S.W.3d)

Coverage varies. In testing:
- Franklyn case (44 authorities): 43 of 44 found (98%)
- Roberts case (83 authorities): 64 of 83 found (77%)

Cases not found are typically recent (2020+), unpublished (WL-only cites), or from less-covered reporters.

## License

MIT License. See [LICENSE](LICENSE) for details.
