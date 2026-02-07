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
   - Key authorities: what they hold and how each side uses them
   - For each side: are the cited authorities on point, or does the argument rely on analogy from different legal contexts? How strong is any analogy?
   - Weaknesses in each side's position
   - Where a brief argues for extending or broadly reading a case, assess the strength of that argument -- this is advocacy, not error
   - How cite-check accuracy findings (not advocacy targets or relevance gaps) affect the analysis
6. **On the briefs**: State which side should win this issue based on the briefing alone (e.g., "On the briefs, the appellant should win this issue because..."). Do not predict outcomes, assign probabilities, or estimate confidence levels.
7. **Oral argument hot spots**: What questions the panel is likely to ask on this issue

## Structure

The analysis should cover every substantive issue raised in the briefs. Common categories in Texas criminal appeals include:
- Error preservation / procedural default
- Substantive standard of review
- Application of the legal standard to the facts
- Harm analysis
- Any ancillary issues (costs, etc.)

## Important Notes
- Read the authority text files in authorities/ to understand what cases hold -- do not rely solely on how either brief characterizes them
- Distinguish between a brief that misrepresents a case's holding and a brief that argues a case should be read broadly or applied to new facts. The former is an error; the latter is advocacy. Evaluate the strength of the advocacy rather than treating it as a citation error.
- When a party cites cases involving different offenses or legal contexts to support an argument by analogy, evaluate the strength of the analogy. Verified citation accuracy does not mean the authority is on point. Note when a string of citations all involve different offenses than the one being briefed.
- The cite-check report distinguishes between accuracy issues, relevance gaps, advocacy targets, and reply-brief critiques. Use these categories in your analysis rather than treating all cite-check findings as errors.
- Flag any cite-check accuracy errors that materially affect the analysis
- Note where authorities are unpublished and whether that matters
- Identify the 2-3 arguments most likely to be decisive

Output the full content of ISSUE_ANALYSIS.md now. Do not use the Write tool. Print it directly to stdout."""


def build_tool_prompt(
    brief_paths: list[str],
    citecheck_path: str,
    authorities_dir: str,
) -> str:
    """Build a tool-based issue analysis prompt.

    Instead of embedding all file contents (which can exceed context limits),
    this tells Claude to read the files itself using tools.
    """
    brief_list = "\n".join(f"- {p}" for p in brief_paths)

    return f"""You are a senior appellate attorney analyzing a Texas criminal appeal for moot court preparation.

## Files to Read

Read each of these files using the Read tool before beginning your analysis:

**Briefs:**
{brief_list}

**Cite-Check Report:**
- {citecheck_path}

**Authority texts are in:**
- {authorities_dir}/

Read all briefs and the cite-check report first. Then read specific authority texts as needed to verify holdings.

## Instructions

Produce a comprehensive ISSUE_ANALYSIS.md organized by issue. For each issue:

1. **State the issue** as the court would frame it
2. **Appellant's argument**: Summarize with key citations
3. **State's response**: Summarize with key citations
4. **Appellant's reply** (if applicable): Summarize
5. **Analysis**:
   - Which side has the stronger argument and why
   - Key authorities: what they hold and how each side uses them
   - For each side: are the cited authorities on point, or does the argument rely on analogy from different legal contexts? How strong is any analogy?
   - Weaknesses in each side's position
   - Where a brief argues for extending or broadly reading a case, assess the strength of that argument -- this is advocacy, not error
   - How cite-check accuracy findings (not advocacy targets or relevance gaps) affect the analysis
6. **On the briefs**: State which side should win this issue based on the briefing alone (e.g., "On the briefs, the appellant should win this issue because..."). Do not predict outcomes, assign probabilities, or estimate confidence levels.
7. **Oral argument hot spots**: What questions the panel is likely to ask on this issue

## Structure

The analysis should cover every substantive issue raised in the briefs. Common categories in Texas criminal appeals include:
- Error preservation / procedural default
- Substantive standard of review
- Application of the legal standard to the facts
- Harm analysis
- Any ancillary issues (costs, etc.)

## Important Notes
- Read the authority text files in {authorities_dir}/ to understand what cases hold -- do not rely solely on how either brief characterizes them
- Distinguish between a brief that misrepresents a case's holding and a brief that argues a case should be read broadly or applied to new facts. The former is an error; the latter is advocacy. Evaluate the strength of the advocacy rather than treating it as a citation error.
- When a party cites cases involving different offenses or legal contexts to support an argument by analogy, evaluate the strength of the analogy. Verified citation accuracy does not mean the authority is on point. Note when a string of citations all involve different offenses than the one being briefed.
- The cite-check report distinguishes between accuracy issues, relevance gaps, advocacy targets, and reply-brief critiques. Use these categories in your analysis rather than treating all cite-check findings as errors.
- Flag any cite-check accuracy errors that materially affect the analysis
- Note where authorities are unpublished and whether that matters
- Identify the 2-3 arguments most likely to be decisive

Output the full content of ISSUE_ANALYSIS.md now. Do not use the Write tool. Print it directly to stdout."""
