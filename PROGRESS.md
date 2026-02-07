# Progress Log

## 2025-02-06 — Pipeline fixes and first full run

### What was done
- Ran full 11-step pipeline on case 14-25-00079-CR (14th COA)
- Fixed 7 infrastructure bugs discovered during the run (see SESSION_NOTES.md)
- Key fixes: ci() grouping, Westlaw download capture, companion case disambiguation, --add-dir hang

### Why
- First real end-to-end test of the pipeline rewrite (commit c92f3e9)
- Each bug was discovered sequentially as the pipeline progressed through steps

### Alternatives considered
- iTerm tab approach for user prompts (abandoned — AppleScript unreliable from Claude Code subprocess)
- Keeping --add-dir for analysis step (abandoned — 10+ hour hang, citecheck excerpts sufficient)

## 2026-02-07 — Cite-checker purpose, advocacy, and relevance awareness

### What was done
- Added `classify_brief_type()` to `file_utils.py` — determines party (appellant/state) and brief type (opening/response/reply) from filename
- Rewrote `EXTRACT_PROMPT` in `s5_citecheck.py` — now extracts `purpose` (supporting/extending/critiquing/background) and `argument_context` per citation, with reply-brief-specific guidance
- Updated `_extract_pairs()` to accept and format brief type into the prompt
- Rewrote `VERIFY_PROMPT` — purpose-aware verification: supporting citations get relevance checks, extending citations are graded as advocacy targets (not errors), critiquing citations verify the critique itself, background citations get light-touch checks
- Updated `_verify_authority()` to pass purpose and argument_context in proposition blocks
- Rewrote `_format_report()` — report now organized into sections: Citation Accuracy, Relevance Gaps, Advocacy Targets, Reply-Brief Critiques, Error Summary Table
- Wired brief type classification into `run()` orchestration
- Updated both `build_prompt()` and `build_tool_prompt()` in `issue_analysis.py` — replaced "actually hold" bias language, added advocacy/relevance evaluation instructions, expanded Analysis section

### Why
Three interrelated biases in the cite-checker:
1. Reply-brief string cites (arguing cases *don't* support the State) were graded as affirmative citation errors
2. Advocacy arguments (extending a holding to new facts) were graded as misrepresentations instead of recognized as advocacy
3. The State's non-trafficking analogous citations were marked "Verified" without flagging that none addressed trafficking

These biases propagated into the issue analysis, where Moreno was called a "material vulnerability" (it's an advocacy target) and the State's analogical argument was uncritically accepted.

### Alternatives considered
- Adding a post-processing pass to reclassify verdicts (rejected — better to extract purpose at extraction time so verification gets the right instructions)
- Separate prompts per purpose type (rejected — single prompt with purpose-specific instructions keeps the architecture simpler)
