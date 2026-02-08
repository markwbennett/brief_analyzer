# Session Notes - 2026-02-08 (Afternoon)

## Work Completed

### DOCX Line-by-Line Cite-Checker (`docx_citecheck.py`)

Continued development of the standalone DOCX cite-checker. This session focused on report quality, verification depth, and usability.

#### 1. Report format: errors only
- Removed all VERIFIED lines from output — report now shows only items requiring human attention
- Renamed section to "Issues Requiring Attention"
- Summary line still shows verified count for context
- Trimmed existing CITECHECK_LINEBY.md from 1712 lines (216KB) to 505 lines
- Commit: `97c8345`

#### 2. Added `--from-json` regeneration
- New `--from-json` flag regenerates a report from saved JSON without re-running Claude
- Final JSON results now saved alongside markdown (`.json` file) after every run
- `docx` positional argument made optional when `--from-json` is used
- Commit: `97c8345`

#### 3. Two-pass verification for indirect case references (NEEDS_SOURCE)
- New `NEEDS_SOURCE` status in the verification prompt
- When Claude encounters an assertion that claims something about cases not provided (e.g., "none of the six opinions analyzes X" checked against the State's Brief), it returns NEEDS_SOURCE with full citations of the needed authorities
- `resolve_needs_source()` parses citations from the detail text, finds them in `authorities/`, and runs a second verification pass
- Cascading NEEDS_SOURCE entries from second-pass results are dropped
- Prompt tightened: NEEDS_SOURCE only for assertions that claim something *about this source* but need a different source to verify — not for assertions simply unrelated to the source
- Tested on paragraph 61: first pass flagged INACCURATE (couldn't verify "none analyzes the statutory-supremacy question" from State's Brief alone); second pass found all 6 unpublished opinions and verified all 14 assertions
- Commit: `62b2d0d`

#### 4. Page numbers via DOCX-to-PDF conversion
- `build_page_map()`: converts DOCX → PDF via `soffice --headless`, extracts text per page with PyMuPDF (`fitz`)
- `find_page_number()`: matches paragraph opening text against page texts to find starting page (1-based)
- Report headings now show "Page X" instead of "Paragraph N"
- Console output shows `p. X` during processing
- Paragraphs spanning pages stay intact — only starting page reported
- Added `pymupdf>=1.24` to requirements.txt
- Commit: `33e7200`

#### 5. Full run on Draft 4
- Ran on `Roberts, Shawn Reply Brief Draft 4.docx`
- 76 paragraphs, 388 assertions, 304 verified, 84 flagged
- Completed in ~27 minutes (Opus 4.6, per-source parallel verification)
- Output: `CITECHECK_DRAFT4.md`, `CITECHECK_DRAFT4.json`, `CITECHECK_DRAFT4.pdf`
- PDF generated with 14pt Equity Text A, Concourse 6 headings, 1.5" margins

## Git Commits Made
- `97c8345` — Report only flagged items, add --from-json regeneration
- `62b2d0d` — Add two-pass verification for indirect case references
- `33e7200` — Add page numbers via DOCX-to-PDF conversion

## Current State
- `docx_citecheck.py` is feature-complete for current needs:
  - Per-source parallel verification (Opus 4.6, no truncation)
  - Two-pass NEEDS_SOURCE resolution
  - Page numbers from PDF rendering
  - Errors-only report format
  - `--from-json` regeneration, `--dry-run`, `--start`/`--limit` for resuming
- Latest run: Draft 4, 84 issues flagged across 36 pages
- All outputs in `/Users/markbennett/Discovery/Roberts, Shawn Reply Brief/`

## Next Session Recommendations
- **Review the 84 flagged items** in CITECHECK_DRAFT4.pdf — many are legitimate cite-check findings (quote errors, pin cite errors, characterization issues)
- **Some flags are false positives** — e.g., UNSUPPORTED for rhetorical characterizations ("the State's worst citation") that are argument, not factual claims. Consider adding a prompt instruction to skip pure advocacy/argument
- **Re-run after Draft 5** with corrections applied
- **Consider deduplication** — some paragraphs generate duplicate flags when the same assertion is checked against multiple sources (e.g., Bell and Hudson both flagged for the same "something less than probable cause" characterization)

## Quick Reference

### CLI Usage
```bash
# Full run
python docx_citecheck.py <brief.docx> [--model opus] [--output FILE]

# Dry run (no Claude calls)
python docx_citecheck.py <brief.docx> --dry-run

# Resume from paragraph N
python docx_citecheck.py <brief.docx> --start N [--limit M]

# Regenerate report from saved JSON
python docx_citecheck.py --from-json results.json [--output FILE]
```

### Key Functions
- `build_page_map(docx_path)` → `list[str]` — DOCX→PDF→page texts
- `find_page_number(text, page_texts)` → `int|None` — paragraph→page lookup
- `verify_paragraph(para_num, text, sources, model, workers, page_num)` — per-source parallel verification
- `resolve_needs_source(para_num, text, assertions, auth_files, model, workers, page_num)` — second-pass for indirect references
- `gather_sources(paragraph, auth_files, record_index, state_brief_text, last_case)` — source collection per paragraph
- `format_report(results)` — errors-only markdown report

### Roberts Project Files
- Project dir: `/Users/markbennett/Discovery/Roberts, Shawn Reply Brief/`
- Draft 4: `Roberts, Shawn Reply Brief Draft 4.docx`
- State's brief: `2026-02-05 - Brief filed - oral argument not requested - State.txt`
- Authorities: `authorities/` (98 .txt files)
- Latest outputs: `CITECHECK_DRAFT4.md`, `.json`, `.pdf`

### PDF Generation
```bash
pandoc --pdf-engine=xelatex -V geometry:margin=1.5in -V documentclass=extarticle \
  -V fontsize=14pt -V mainfont="Equity Text A" -V sansfont="Concourse 6" \
  -o output.pdf input.md
```
