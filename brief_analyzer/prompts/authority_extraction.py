"""Prompt template for authority extraction (Step 2)."""


def build_prompt(brief_texts: dict[str, str]) -> str:
    """Build the authority extraction prompt.

    Args:
        brief_texts: dict mapping filename -> text content for all .txt files
    """
    file_listing = ""
    for name, content in sorted(brief_texts.items()):
        file_listing += f"\n\n--- BEGIN {name} ---\n{content}\n--- END {name} ---\n"

    return f"""You are a legal research assistant analyzing Texas appellate briefs and related filings.

I am providing you with all text files from a Texas appellate case. Some are briefs (opening, response, reply), some are letters (supplemental authority, correction letters), and some may be notices or other filings.

Your task:
1. First, identify which files are substantive filings (briefs and letters containing legal arguments or authority citations) vs. procedural notices. List the substantive filings.
2. Read all substantive filings carefully.
3. Produce an AUTHORITIES.md file with the following structure:

## Format for AUTHORITIES.md

### Cases

For each unique case cited across all filings:

**Case Name, Reporter Citation (Court Year, disposition)**
- Cited by: [which filing(s)]
- Proposition: [what it is cited for, in each filing]

### Westlaw Search Terms

Provide ci() search strings containing ALL citations. Westlaw's ci() function works with every citation format: S.W.2d/S.W.3d, U.S., F.2d/F.3d/F.4th, F.Supp./F.Supp.2d, F.Appx, A.2d, N.E.2d, P.2d, and Westlaw-only (YYYY WL NNNNNNN). Use space-separated quoted citations inside the ci() call (no OR operator needed).

IMPORTANT: In the ci() search strings, use Westlaw citation format -- no spaces within reporter abbreviations:
- F.Supp. (not F. Supp.)
- F.Supp.2d (not F. Supp. 2d)
- F.Appx (not F. App'x or F. App'x)
The case listing above should use standard legal citation format, but the ci() search strings must use Westlaw format.

If there are more than 40 citations, split into multiple ci() groups of ~40 each and label them Group 1, Group 2, etc.

Example: ci("845 S.W.2d 874" "328 U.S. 750" "2025 WL 3127402" "652 F.3d 557" "827 F.Supp. 372" "479 F.Appx 612")

Note: The user must set the Westlaw data source to "All State & Federal" before running the search.

### Statutes and Rules

Table of all statutes and rules cited, with who cited them and the proposition.

### Treatises and Secondary Sources

Table of any treatises or secondary sources cited.

## Important Notes
- Do NOT number the case entries
- Include the full citation with court, year, and disposition (pet. ref'd, no pet., etc.) when available from the briefs
- If different briefs cite the same case for different propositions, list all propositions
- If a brief misidentifies a court (e.g., says CCA when it's actually a court of appeals), note the citation as given in the brief

## Files

{file_listing}

Output the full content of AUTHORITIES.md now. Do not use the Write tool. Print it directly to stdout."""
