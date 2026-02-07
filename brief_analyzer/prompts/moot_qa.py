"""Prompt template for moot court Q&A generation (Step 7)."""


def build_prompt(
    brief_texts: dict[str, str],
    issue_analysis_text: str,
    citecheck_text: str,
) -> str:
    """Build the moot court Q&A prompt.

    Args:
        brief_texts: dict mapping filename -> text content for all briefs
        issue_analysis_text: content of ISSUE_ANALYSIS.md
        citecheck_text: content of CITECHECK.md
    """
    file_listing = ""
    for name, content in sorted(brief_texts.items()):
        file_listing += f"\n\n--- BEGIN {name} ---\n{content}\n--- END {name} ---\n"

    return f"""You are a seasoned appellate judge preparing for oral argument in a Texas criminal appeal. You have read all the briefs, the issue analysis, the cite-check report, and all cited authorities (available in authorities/).

## Briefs and Filings

{file_listing}

## Issue Analysis

{issue_analysis_text}

## Cite-Check Report

{citecheck_text}

## Instructions

Produce MOOT_QA.md -- a comprehensive moot court preparation document. Structure it as follows:

### Part One: Questions for Appellant
For each question:
- **Q**: The question as a judge would ask it
- **Why the court asks this**: What concern or issue motivates this question
- **Suggested answer**: The strongest response, with citations
- **Follow-up**: The likely follow-up question
- **Trap to avoid**: What NOT to say and why

### Part Two: Questions for the State/Appellee
Same format as Part One.

### Part Three: Questions for Either Side
Questions that could be directed to either party, same format.

### Part Four: Rapid-Fire Preparation
10 short-answer questions with concise (1-2 sentence) answers for quick review.

### Part Five: The Questions That Will Decide the Case
Identify the 3 questions that are most likely to determine the outcome. For each:
- The question
- Why it matters
- How each side should answer
- What the answer likely is

## Guidelines
- Frame questions as a judge would -- pointed, specific, testing the limits of each argument
- Use the cite-check findings to craft questions that expose weaknesses
- Include questions about the implications of ruling for each side
- Include questions about unpublished authorities and their weight
- Include questions that test whether counsel knows the record
- Questions should reflect the actual issues and authorities in THIS case
- Read key authorities in authorities/ to craft precise questions about holdings
- Aim for 10-15 questions per side in Parts One and Two

Output the full content of MOOT_QA.md now. Do not use the Write tool. Print it directly to stdout."""
