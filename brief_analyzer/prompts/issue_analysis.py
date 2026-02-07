"""Prompt template for issue analysis (Step 6)."""


def build_prompt(
    brief_texts: dict[str, str],
    citecheck_text: str,
) -> str:
    """Build the issue analysis prompt.

    Args:
        brief_texts: dict mapping filename -> text content for all briefs
        citecheck_text: content of CITECHECK.md
    """
    file_listing = ""
    for name, content in sorted(brief_texts.items()):
        file_listing += f"\n\n--- BEGIN {name} ---\n{content}\n--- END {name} ---\n"

    return f"""You are a senior appellate attorney analyzing a Texas criminal appeal for moot court preparation. You have access to all briefs, the cite-check report, and the full text of all cited authorities in the authorities/ directory.

## Briefs and Filings

{file_listing}

## Cite-Check Report

{citecheck_text}

## Instructions

Produce a comprehensive ISSUE_ANALYSIS.md organized by issue. For each issue:

1. **State the issue** as the court would frame it
2. **Appellant's argument**: Summarize with key citations
3. **State's response**: Summarize with key citations
4. **Appellant's reply** (if applicable): Summarize
5. **Analysis**:
   - Which side has the stronger argument and why
   - Key authorities and what they actually hold (informed by cite-check findings)
   - Weaknesses in each side's position
   - How the cite-check findings affect the analysis
6. **Prediction**: Likely outcome on this issue with confidence level
7. **Oral argument hot spots**: What questions the panel is likely to ask on this issue

## Structure

The analysis should cover every substantive issue raised in the briefs. Common categories in Texas criminal appeals include:
- Error preservation / procedural default
- Substantive standard of review
- Application of the legal standard to the facts
- Harm analysis
- Any ancillary issues (costs, etc.)

## Important Notes
- Read the actual authority text files in authorities/ to verify what cases hold -- do not rely solely on how the briefs characterize them
- Flag any cite-check errors that materially affect the analysis
- Note where authorities are unpublished and whether that matters
- Identify the 2-3 arguments most likely to be decisive

Output the full content of ISSUE_ANALYSIS.md now. Do not use the Write tool. Print it directly to stdout."""
