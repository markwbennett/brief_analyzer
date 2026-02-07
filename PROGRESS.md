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
