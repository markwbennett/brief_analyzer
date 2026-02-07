# Session Notes - 2026-02-07

## Work Completed

### Cite-checker purpose, advocacy, and relevance awareness

Addressed three interrelated biases in the cite-check pipeline that caused it to penalize advocacy as error and miss relevance gaps:

#### 1. Added `classify_brief_type()` to `file_utils.py` (line 120)
- Determines party (`appellant`/`state`/`unknown`) and brief type (`opening`/`response`/`reply`/`unknown`) from filename
- Used to provide context to the extraction prompt

#### 2. Rewrote `EXTRACT_PROMPT` in `s5_citecheck.py` (line 24)
- Now includes brief type/party context at the top
- Extracts two new fields per citation:
  - `purpose`: `supporting` | `extending` | `critiquing` | `background`
  - `argument_context`: 1-sentence description of the legal argument
- `REPLY_GUIDANCE` constant (line 60) provides reply-brief-specific classification hints
- Reply briefs get guidance that string cites after "the State relies on..." are likely `critiquing`

#### 3. Updated `_extract_pairs()` in `s5_citecheck.py` (line 76)
- Accepts `brief_type: dict` parameter
- Formats brief type article/label/party and reply guidance into the prompt

#### 4. Rewrote `VERIFY_PROMPT` in `s5_citecheck.py` (line 203)
- Purpose-specific evaluation:
  - **supporting**: standard check PLUS relevance check (`on_point`/`analogous`/`off_point`)
  - **extending**: graded as `Advocacy` (not an error), with `advocacy_gap` description
  - **critiquing**: graded as `Critique-Valid` or `Critique-Questionable`
  - **background**: light-touch check
- New JSON output fields: `purpose`, `relevance`, `relevance_note`, `advocacy_gap`

#### 5. Updated `_verify_authority()` in `s5_citecheck.py` (line 249)
- Passes `purpose` and `argument_context` in the proposition block sent to Claude

#### 6. Rewrote `_format_report()` in `s5_citecheck.py` (line 348)
- Report organized into sections:
  - **Citation Accuracy**: real errors (Minor/Moderate/Significant/Critical)
  - **Relevance Gaps**: verified citations where authority is analogous/off_point
  - **Advocacy Targets**: extending citations with gap descriptions
  - **Reply-Brief Critiques**: critiquing citations with validity assessment
  - **Error Summary Table**: accuracy errors only
- Summary line includes counts for each category

#### 7. Wired up brief type in `run()` (line 530)
- Classifies each brief after `find_brief_texts()`
- Passes brief type to `_extract_pairs()`
- Purpose/context flows through grouping to verification unchanged

#### 8. Updated `issue_analysis.py` — both `build_prompt()` and `build_tool_prompt()`
- Replaced "actually hold" with "what they hold and how each side uses them"
- Replaced "Read the actual authority text files...to verify" with "...to understand"
- Added to Important Notes:
  - Distinguish misrepresentation (error) from broad reading (advocacy)
  - Evaluate analogical strength when authorities involve different offenses
  - Use cite-check report categories (accuracy/relevance/advocacy/critique) rather than treating all findings as errors
- Expanded Analysis section with analogy evaluation and advocacy assessment

## Git Commits Made
- (pending — this session)

## Current State
- All changes made, imports verified, `classify_brief_type()` tested against actual case filenames
- `CITECHECK.md` and `ISSUE_ANALYSIS.md` in `~/Discovery/14-25-00079-CR/` need to be deleted and re-generated to see the new behavior
- Pipeline architecture unchanged: same parallel execution, retry logic, authority matching

## Next Session Recommendations
- Delete `CITECHECK.md` and re-run `--step citecheck` on 14-25-00079-CR to verify:
  - Reply-brief string cites (Jefferson, Jourdan, Landrian, Pizzo, Vick, Young) appear under "Reply-Brief Critiques"
  - Moreno, Castoreno, Barnes etc. appear under "Advocacy Targets"
  - State's non-trafficking citations flagged under "Relevance Gaps"
- Delete `ISSUE_ANALYSIS.md` and re-run `--step analysis` to verify Moreno is treated as advocacy, State's analogical argument is evaluated for strength
- Consider whether `classify_brief_type()` needs additional patterns for other jurisdictions/filing conventions
- The `--force` flag recommendation from last session still stands

## Quick Reference

### New/Modified Functions
- `classify_brief_type(filename) -> dict` — `file_utils.py:120` — returns `{party, brief_type}`
- `_extract_pairs(brief_name, brief_text, model, brief_type)` — `s5_citecheck.py:76` — now accepts brief_type
- `_verify_authority(authority_file, authority_text, propositions, model)` — `s5_citecheck.py:249` — now passes purpose/context
- `_format_report(brief_name, pairs)` — `s5_citecheck.py:348` — sectioned report format

### New Severity Grades
- `Advocacy` — extending citations (not an error)
- `Critique-Valid` — reply-brief critique is accurate
- `Critique-Questionable` — reply-brief critique is debatable

### New Citation Fields (extraction)
- `purpose`: `supporting` | `extending` | `critiquing` | `background`
- `argument_context`: 1-sentence legal argument description

### New Verification Fields
- `relevance`: `on_point` | `analogous` | `off_point`
- `relevance_note`: explanation of relevance gap
- `advocacy_gap`: what case holds vs. what brief argues (extending only)
