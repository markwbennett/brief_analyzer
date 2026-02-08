# Session Notes - 2026-02-08

## Work Completed

### Roberts, Shawn Reply Brief (14-25-00061-CR)

#### 1. Added `--brief` filter to citecheck step
- `cli.py`: new `--brief` argument (substring match on brief filename)
- `config.py`: new `brief_filter: Optional[str]` field on `ProjectConfig`
- `s5_citecheck.py`: `run()` filters `txt_files` when `brief_filter` is set; skips the "already exists" check so CITECHECK.md is overwritten on targeted reruns
- Usage: `python -m brief_analyzer <dir> --step citecheck --brief "Reply"`

#### 2. Fixed extraction prompt to capture per-use citations
- The extraction prompt was producing one entry per case name instead of one per citation instance
- Added explicit instruction: "If the same case is cited multiple times for different propositions, different pin cites, or different quotations, output a SEPARATE entry for EACH use. This applies even when multiple cites appear in the same sentence or paragraph."
- Result: Gilmore went from 1 proposition to 6; total extractions from reply brief went from 21 to 39
- The Gilmore sign-quotation inaccuracy was caught on rerun (Moderate)

#### 3. Improved JSON parsing robustness
- Extracted `_parse_json_array()` as a shared utility (replaces duplicated parsing in both `_extract_pairs` and `_verify_authority`)
- Uses bracket-depth matching instead of greedy regex to find JSON arrays in responses with reasoning preamble
- Added "Your response must begin with [ and end with ]" to both EXTRACT_PROMPT and VERIFY_PROMPT

#### 4. Added diagnostic logging for verification failures
- `_verify_authority()` now logs the specific failure mode: API error (with exit code), empty output, empty JSON array, or unparseable response (with first 200 chars)
- Previously all failures were silently retried with no indication of cause

#### 5. Generated REPLY_OUTLINE.md and PDF
- New standalone script: `scripts/reply_outline.py`
- Usage: `python scripts/reply_outline.py <project_dir>`
- Uses `claude --print --model opus` with `--allowedTools Read,Bash(ls:*)` and `--add-dir` for project and authorities directories
- Reads both briefs and selectively reads authorities to produce a detailed reply-brief argument outline with the A-E structure per issue
- Outputs REPLY_OUTLINE.md and REPLY_OUTLINE.pdf
- Generated 31KB outline covering both points of error with specific pin cites and quotable language

#### 6. Westlaw searches and new authority evaluation
- Ran three Westlaw T&C searches for pat-down/magnetometer cases involving jail/prison visitors
- Downloaded 20 cases from two search result sets (third search returned nothing)
- Processed RTFs through rtf2text
- Evaluated all 15 new cases; kept 8 useful ones, deleted 7 irrelevant ones
- Cleaned up 3 bad symlinks created by rtf2text incorrectly matching new cases to AUTHORITIES.md entries

#### 7. Processed manually added authorities
- User added RTFs for Florida v. Jimeno, U.S. v. Aukai, U.S. v. Spriggs, McMorris v. Alioto
- All converted and renamed with proper citations

### Key new authorities found (not in original briefs)
- **Gadson v. State, 668 A.2d 22 (Md. 1995)** — Maryland highest court; visitor tried to leave checkpoint, trooper refused; held detention unconstitutional absent individualized suspicion; rejected Turnbeaugh "one-way street" argument
- **State v. Garcia, 116 N.M. 87 (N.M. Ct. App. 1993)** — visitor refused strip search; officials must escort her out, not detain; suppression when departure option not honored
- **State v. Dane, 89 Wash.App. 226 (Wash. Ct. App. 1997)** — correctional officers had no authority to detain visitor beyond offering consent-or-leave; follows Garcia
- **Jordan ex rel. Johnson v. Taylor, 310 F.3d 1068 (8th Cir. 2002)** — 8th Circuit; visitor encounter consensual when free to leave; no search where no coercion
- **Neumeyer v. Beard, 421 F.3d 210 (3d Cir. 2005)** — 3d Circuit; upholds vehicle searches but fn.2 expressly reserves person-searches; consent-or-leave framework

## Git Commits Made
- (pending — to be committed at end of session)

## Current State
- `CITECHECK.md` in Roberts project: reply-brief-only, 39 citations, 11 accuracy issues, all verified
- `REPLY_OUTLINE.md` and `.pdf` generated; covers both points of error
- 108 authority .txt files in authorities/ (after adding new WL search results and deleting irrelevant ones)
- Code changes: `--brief` filter, extraction prompt fix, JSON parsing consolidation, diagnostic logging
- `scripts/reply_outline.py` created as standalone tool

## Next Session Recommendations
- **Regenerate REPLY_OUTLINE** with reframing: lead with the detention (seizure), not the search intrusiveness; use strip-search cases in supporting role only; incorporate Gadson, Garcia, Dane, Jordan, Neumeyer
- **Run full 3-brief citecheck** with the fixed extraction prompt to get complete report
- **Consider adding `--force` flag** to pipeline steps to overwrite existing output without manual deletion
- **Consider adding a "stop on missing authorities" check** — user noted the pipeline should abort when authorities are missing rather than proceeding with wrong matches
- **The `_parse_json_array` bracket-matching approach** should prevent most JSON-slip retries, but monitor whether opus still occasionally slips into reasoning mode on large authority texts

## Quick Reference

### New CLI Arguments
- `--brief <substring>`: filter citecheck to matching brief(s) only

### New/Modified Functions
- `_parse_json_array(text, label) -> list[dict]` — `s5_citecheck.py:78` — shared JSON extraction with bracket-depth matching
- `run(config)` in s5_citecheck.py — now respects `config.brief_filter`

### New Script
- `scripts/reply_outline.py <project_dir>` — standalone reply-brief outline generator using opus with tool access

### Roberts Project Files
- Project dir: `/Users/markbennett/Discovery/Roberts, Shawn Reply Brief/`
- Opening brief: `2025-12-29 - Brief filed - oral argument requested - Appellant.txt`
- State's brief: `2026-02-05 - Brief filed - oral argument not requested - State.txt`
- Reply draft: `Roberts, Shawn Reply Brief Draft — cited.txt`
- Authorities: `authorities/` (108 .txt files)
- Outputs: `CITECHECK.md`, `REPLY_OUTLINE.md`, `REPLY_OUTLINE.pdf`, `AUTHORITIES.md`
