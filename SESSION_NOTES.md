# Session Notes - 2026-02-08 (Evening)

## Work Completed

### 1. Cite-Check Run on Draft 6
- Ran `docx_citecheck.py` on Roberts, Shawn Reply Brief Draft 6.docx
- Initial run: 75 paragraphs, 349 assertions, 286 verified, 63 flagged
- Output: `CITECHECK_DRAFT6.md`, `.json`, `.pdf`

### 2. Substantive Brief Revisions (user made edits based on cite-check review)

#### Detention/seizure framing (paras 72, 82, 84, 85)
- Replaced "assumes a willing visitor" and "does not try" language
- New framing: State "treats the authority to detain as flowing from the authority to search" and "assumes what it must prove"
- "Grant all three arguendo. They do not justify the seizure."
- Core point preserved ("The State never does. It never tries.") but aimed at the seizure, not the detention generally

#### Cates paragraph rewritten (para 133)
- State's actual argument: Roberts was in a more secure area than Cates visitor
- State mischaracterizes Cates facts (says Cates was where contraband transfer was possible; Ninth Circuit said opposite)
- But it doesn't matter — Cates holding is departure-dependent, not location-dependent
- "or who was leaving the prison" clause is independent
- Pin cite corrected: holding is at 982, not 982–83

#### Other fixes made by user:
- "Bouncer" → "private security guard" / "nightclub-security-guard case" throughout
- "Much less invasive" → "significantly less intrusive" (para 135, State's Br. at 28)
- Aukai paragraph rewritten: no false origin claim for "one-way street" metaphor, no "irrevocable consent," uses actual Aukai language about terrorists probing for "a vulnerable portal"
- Spear/warrant: removed warrant-requirement sentence from under Spear's umbrella; Ferguson now carries the law-enforcement purpose argument; Spear pin cite corrected to 630
- State's Br. pin cite: 37–39 → 43–46 (para 195)
- Herzbrun pin cite: 774 → 778 n.8 (para 152)
- Spear pin cite: 633 → 632 (para 154)
- Gilmore "held" → "observed" (para 94, re: footnote 4)
- "Routine exercise" → "an exercise" (para 141)
- State's Br. capitalization: "article" → "[a]rticle" with brackets (para 159)

### 3. Page Segmentation Fix to Cite-Checker
- Added `segment_by_pages()` function to `docx_citecheck.py`
- Replaces inline `*NNN` Westlaw page markers with explicit `[PAGE NNN]` headers
- Applied in `verify_paragraph()` before sending source text to Claude
- Updated prompt instruction 5 to explain page headers and pin cite verification
- Commit: `9e4758f`

### 4. Second Cite-Check Run (with page segmentation)
- Re-ran on updated Draft 6: 75 paragraphs, 300 assertions, 245 verified, 55 flagged (down from 63)
- Page segmentation caught new pin cite errors the first run missed
- Output: `CITECHECK_DRAFT6B.md`, `.json`, `.pdf`

## New Pin Cite Errors Caught by Page Segmentation
- James v. Illinois, Id. at 318 → should be **317–18** ("significantly weaken" starts on 317)
- James v. Illinois, Id. at 315 → should be **314** ("mere threat of perjury" is on 314)
- Cates, 976 F.3d at 982 (para 121) → should be **982–83** (quotes span both pages)

## Remaining Issues to Address in Draft 7

### Must Fix
1. **James pin cites**: 318 → 317–18; 315 → 314
2. **Cates pin cite (para 121)**: 982 → 982–83
3. **Rouse "specific objective facts" (p. 22)**: check that "Id." chain points to Rouse, not Cates
4. **Harris v. State and Gillon pin cite (p. 30)**: checker says Harris at p. 42 fn. 6, Gillon at p. 43, not pp. 33–35
5. **Gilmore consent-form quote order (p. 19)**: brief reorders items; source order is "X-ray devices, metal detectors, body scanners, and pat down searches"

### Judgment Calls
- Lee v. State "was not compelled to" quote — truncation omits conditional framing
- Gilmore 1257 quote — court agreeing with sister circuits, not independent holding
- "They did not station an officer at the entrance" — RR9:58 doesn't address this (absence of evidence)

### Not Fixable (video exhibit)
- SX10 citations throughout — video not available to checker

## Git Commits Made
- `9e4758f` — Add page segmentation for pin cite verification

## Current State
- Draft 6 has been substantially revised by user during this session
- Two cite-check reports available: CITECHECK_DRAFT6.md (pre-segmentation) and CITECHECK_DRAFT6B.md (post-segmentation)
- Page segmentation feature working and catching real pin cite errors
- Word count in certificate of compliance (3,644) is stale — needs updating after edits

## Key Files
- Draft 6: `/Users/markbennett/Discovery/Roberts, Shawn Reply Brief/Roberts, Shawn Reply Brief Draft 6.docx`
- Cite-check reports: `CITECHECK_DRAFT6.md`, `CITECHECK_DRAFT6B.md` (and `.json`, `.pdf`)
- State's Brief: `2026-02-05 - Brief filed - oral argument not requested - State.txt`
- Authorities: `authorities/` (98+ .txt files)

## Next Session Recommendations
- Fix the 5 "must fix" items listed above
- Re-run cite-checker after fixes for a clean report
- Update word count in certificate of compliance
- Consider whether Gilmore consent-form quote order matters enough to fix (it's in quotation marks, so technically yes)
