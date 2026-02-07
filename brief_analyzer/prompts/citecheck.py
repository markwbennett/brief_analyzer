"""Prompt template for cite-checking (Step 5)."""

from pathlib import Path


def build_prompt(
    brief_name: str,
    brief_text: str,
    authorities_dir: Path,
) -> str:
    """Build the cite-check prompt for a single brief.

    Args:
        brief_name: filename of the brief being checked
        brief_text: full text of the brief
        authorities_dir: path to directory containing authority .txt files
    """
    return f"""You are a meticulous legal cite-checker analyzing a Texas appellate brief. Your job is to verify every citation in this brief against the actual authority text files in the authorities/ directory.

## Brief Under Review

**{brief_name}**

{brief_text}

## Instructions

For every citation in this brief:

1. **Identify the citation**: case name, reporter cite, pin cite (if any)
2. **Find the authority**: Read the corresponding .txt file in the authorities/ directory. Use `ls` to find the right file if the exact name isn't obvious.
3. **Verify each of these**:
   - **Reporter citation accuracy**: Is the volume/reporter/page correct?
   - **Pin cite accuracy**: Does the quoted material or proposition actually appear at the cited page?
   - **Quotation accuracy**: If the brief quotes the authority, is the quotation verbatim? Note any additions, omissions, or alterations.
   - **Proposition accuracy**: Does the authority actually stand for the proposition the brief cites it for? Is the characterization fair and accurate?
   - **Court identification**: Is the court correctly identified (e.g., CCA vs. Court of Appeals)?
   - **Year accuracy**: Is the year correct?
   - **Disposition accuracy**: Is the disposition (pet. ref'd, no pet., etc.) correct?

4. **Grade each error found**:
   - **Critical**: Authority does not support the proposition cited, or court/holding is materially misidentified
   - **Significant**: Quotation materially altered, or pin cite is wrong and misleading
   - **Moderate**: Minor quotation differences, slightly imprecise characterization
   - **Minor**: Typos in citations, formatting issues, year off by one

## Output Format

Produce a structured report:

### [Brief Name] -- Cite-Check Report

**Summary**: X citations checked, Y errors found (Z critical, W significant, ...)

#### Citation 1: [Case Name], [Citation]
- **Cited for**: [proposition as stated in brief]
- **Verified**: [YES/NO]
- **Issues**: [description of any problems found]
- **Severity**: [Critical/Significant/Moderate/Minor]
- **Details**: [specific evidence from the authority text]

[Repeat for each citation]

#### Error Summary Table

| # | Citation | Issue | Severity |
|---|----------|-------|----------|
| 1 | ... | ... | ... |

Check every single citation. Do not skip any. Read the actual authority text files -- do not rely on your training data for what cases hold."""
