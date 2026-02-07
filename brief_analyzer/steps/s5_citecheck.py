"""Step 5: Cite-check briefs against authority texts.

Three-phase approach:
  5a. Claude extracts citation-proposition pairs from each brief (structured JSON).
  5b. Python mechanically verifies: reporter cites, years, courts, quotations.
  5c. Claude reviews only the ambiguous/failed cases for proposition accuracy.
"""

import json
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ..config import ProjectConfig
from ..utils.file_utils import find_brief_texts


# --- Phase A: Extract citation-proposition pairs ---

EXTRACT_PROMPT = """You are a legal citation extractor. Read this brief and extract every case citation with its context.

For each citation, output a JSON object with these fields:
- case_name: the case name as cited (e.g., "Theus v. State")
- volume: reporter volume number (e.g., "845")
- reporter: reporter abbreviation (e.g., "S.W.2d", "U.S.", "F.3d", "WL")
- page: starting page or WL number (e.g., "874", "3127402")
- pin_cite: specific page cited, if any (e.g., "at 878"); empty string if none
- court: court as identified in the brief (e.g., "Tex. Crim. App.", "Tex. App.--Houston [1st Dist.]")
- year: year as cited (e.g., "1992")
- disposition: disposition if given (e.g., "pet. ref'd", "no pet.")
- proposition: what the brief cites this case for (1-2 sentences)
- quotation: any direct quotation from the case (verbatim from the brief); empty string if none
- brief_page: approximate location in the brief (page number or section)

Output ONLY a JSON array. No commentary, no markdown fencing. Just the raw JSON array.

BRIEF TEXT:

{brief_text}"""


def _extract_pairs(brief_name: str, brief_text: str, model: str) -> list[dict]:
    """Phase A: Use Claude to extract citation-proposition pairs."""
    prompt = EXTRACT_PROMPT.format(brief_text=brief_text)

    cmd = ["claude", "--print", "--model", model]
    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  Extract failed for {brief_name}: {result.stderr[:200]}", file=sys.stderr)
        return []

    text = result.stdout.strip()
    # Strip markdown code fencing if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    try:
        pairs = json.loads(text)
        if isinstance(pairs, list):
            return pairs
    except json.JSONDecodeError as e:
        print(f"  JSON parse failed for {brief_name}: {e}", file=sys.stderr)
        # Try to salvage: find the array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    return []


# --- Phase B: Mechanical verification ---

def _find_authority_file(case_name: str, volume: str, reporter: str, page: str,
                         auth_files: dict[str, str]) -> tuple[str, str] | None:
    """Find the matching authority file by citation components.

    Returns (filename, text) or None.
    """
    # Try matching by volume/reporter/page in filename
    cite_pattern = f"{volume} {reporter} {page}" if reporter != "WL" else f"{page}"

    for fname, text in auth_files.items():
        if cite_pattern in fname:
            return (fname, text)

    # Try matching by case name (first party before "v.")
    if case_name:
        first_party = case_name.split(" v.")[0].split(" v ")[0].strip()
        if first_party:
            # Normalize for matching
            first_lower = first_party.lower().split()[-1]  # last word of first party
            for fname, text in auth_files.items():
                if first_lower in fname.lower():
                    return (fname, text)

    # Try matching by citation in file content
    for fname, text in auth_files.items():
        header = text[:2000]
        if volume and reporter and page:
            if reporter == "WL":
                if f"WL {page}" in header:
                    return (fname, text)
            elif f"{volume} {reporter} {page}" in header:
                return (fname, text)

    return None


def _verify_citation(pair: dict, auth_files: dict[str, str]) -> dict:
    """Mechanically verify a single citation-proposition pair.

    Returns a result dict with verification status and any issues found.
    """
    result = {
        "citation": f"{pair.get('case_name', '?')}, {pair.get('volume', '')} {pair.get('reporter', '')} {pair.get('page', '')}",
        "proposition": pair.get("proposition", ""),
        "issues": [],
        "verified_mechanically": [],
        "needs_claude_review": False,
        "authority_file": None,
        "authority_excerpt": "",
    }

    case_name = pair.get("case_name", "")
    volume = pair.get("volume", "")
    reporter = pair.get("reporter", "")
    page = pair.get("page", "")
    pin_cite = pair.get("pin_cite", "")
    court = pair.get("court", "")
    year = pair.get("year", "")
    quotation = pair.get("quotation", "")

    # Find the authority file
    match = _find_authority_file(case_name, volume, reporter, page, auth_files)
    if not match:
        result["issues"].append({
            "type": "authority_not_found",
            "severity": "Critical",
            "detail": f"No authority file found for {result['citation']}",
        })
        result["needs_claude_review"] = True
        return result

    fname, auth_text = match
    result["authority_file"] = fname
    header = auth_text[:3000]

    # Check reporter citation in authority text
    if volume and reporter and page and reporter != "WL":
        cite_str = f"{volume} {reporter} {page}"
        if cite_str in auth_text:
            result["verified_mechanically"].append("reporter_cite")
        else:
            result["issues"].append({
                "type": "reporter_cite_mismatch",
                "severity": "Significant",
                "detail": f"Citation '{cite_str}' not found in authority text",
            })

    # Check year
    if year:
        if year in header:
            result["verified_mechanically"].append("year")
        else:
            result["issues"].append({
                "type": "year_mismatch",
                "severity": "Minor",
                "detail": f"Year '{year}' not found in authority header",
            })

    # Check court identification
    if court:
        court_checks = {
            "Tex. Crim. App.": [r"Court\s+of\s+Criminal\s+Appeals", r"Tex\.\s*Crim\.\s*App"],
            "Tex. App.": [r"Court\s+of\s+Appeals"],
            "U.S.": [r"Supreme\s+Court.*United\s+States"],
        }
        court_found = False
        for court_key, patterns in court_checks.items():
            if court_key in court:
                for pat in patterns:
                    if re.search(pat, header, re.IGNORECASE):
                        court_found = True
                        break
                if court_found:
                    result["verified_mechanically"].append("court")
                else:
                    # Check if a DIFFERENT court is identified
                    if "Court of Criminal Appeals" in header and "Tex. App." in court:
                        result["issues"].append({
                            "type": "court_misidentified",
                            "severity": "Critical",
                            "detail": f"Brief says '{court}' but authority is from CCA",
                        })
                    elif "Court of Appeals" in header and "Crim. App." in court:
                        result["issues"].append({
                            "type": "court_misidentified",
                            "severity": "Critical",
                            "detail": f"Brief says '{court}' but authority is from Court of Appeals",
                        })
                    else:
                        result["needs_claude_review"] = True
                break

    # Check quotation accuracy
    if quotation and len(quotation) > 20:
        # Normalize whitespace for comparison
        q_norm = re.sub(r"\s+", " ", quotation.strip())
        a_norm = re.sub(r"\s+", " ", auth_text)

        if q_norm in a_norm:
            result["verified_mechanically"].append("quotation_verbatim")
        else:
            # Try with some fuzzy matching -- strip punctuation differences
            q_stripped = re.sub(r"[.,;:!?\"\'\-\u2014\u2013\u2018\u2019\u201c\u201d]", "", q_norm).lower()
            a_stripped = re.sub(r"[.,;:!?\"\'\-\u2014\u2013\u2018\u2019\u201c\u201d]", "", a_norm).lower()

            if q_stripped in a_stripped:
                result["verified_mechanically"].append("quotation_minor_diffs")
            else:
                # Check if at least 80% of words match in sequence
                q_words = q_stripped.split()
                if len(q_words) >= 5:
                    # Check for substantial substring match
                    midpoint = len(q_words) // 2
                    mid_phrase = " ".join(q_words[midpoint:midpoint+5])
                    if mid_phrase in a_stripped:
                        result["issues"].append({
                            "type": "quotation_altered",
                            "severity": "Moderate",
                            "detail": "Quotation found in authority but with differences",
                        })
                        result["needs_claude_review"] = True
                    else:
                        result["issues"].append({
                            "type": "quotation_not_found",
                            "severity": "Significant",
                            "detail": "Quoted text not found in authority",
                        })
                        result["needs_claude_review"] = True
                        # Save excerpt for Claude review
                        result["authority_excerpt"] = auth_text[:5000]

    # Proposition accuracy always needs Claude review
    if pair.get("proposition"):
        result["needs_claude_review"] = True
        if not result["authority_excerpt"]:
            result["authority_excerpt"] = auth_text[:5000]

    return result


# --- Phase C: Claude review of ambiguous cases ---

REVIEW_PROMPT = """You are a legal cite-checker reviewing flagged citations. For each citation below, I provide:
- The citation and proposition as stated in the brief
- Any mechanical issues found
- An excerpt from the authority text

For each, assess:
1. Does the authority actually support the proposition cited? (Critical if not)
2. Is the characterization fair and accurate? (Significant if misleading)
3. Are there any other issues?

Grade each: Verified / Critical / Significant / Moderate / Minor

Output a JSON array with one object per citation:
{{"citation": "...", "proposition_accurate": true/false, "severity": "Verified|Critical|Significant|Moderate|Minor", "explanation": "..."}}

Output ONLY the JSON array.

CITATIONS TO REVIEW:

{review_items}"""


def _claude_review(items: list[dict], model: str) -> list[dict]:
    """Phase C: Send ambiguous citations to Claude for review."""
    if not items:
        return []

    review_text = ""
    for i, item in enumerate(items, 1):
        review_text += f"\n--- Citation {i} ---\n"
        review_text += f"Citation: {item['citation']}\n"
        review_text += f"Proposition: {item['proposition']}\n"
        if item["issues"]:
            review_text += f"Mechanical issues: {json.dumps(item['issues'])}\n"
        if item["authority_excerpt"]:
            review_text += f"Authority excerpt:\n{item['authority_excerpt']}\n"

    prompt = REVIEW_PROMPT.format(review_items=review_text)
    cmd = ["claude", "--print", "--model", model]
    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True)

    if result.returncode != 0:
        return []

    text = result.stdout.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return []


# --- Orchestration ---

def _process_one_brief(args: tuple) -> tuple[str, str]:
    """Process a single brief through all three phases."""
    brief_name, brief_text, authorities_dir_str, model = args
    auth_dir = Path(authorities_dir_str)

    # Load all authority texts
    auth_files = {}
    for f in sorted(auth_dir.glob("*.txt")):
        auth_files[f.name] = f.read_text(errors="replace")

    # Phase A: Extract pairs
    print(f"  [{brief_name}] Extracting citations...")
    pairs = _extract_pairs(brief_name, brief_text, model)
    if not pairs:
        return (brief_name, f"Failed to extract citations from {brief_name}")

    print(f"  [{brief_name}] Found {len(pairs)} citations. Verifying mechanically...")

    # Phase B: Mechanical verification
    results = []
    for pair in pairs:
        result = _verify_citation(pair, auth_files)
        results.append(result)

    # Phase C: Claude review for ambiguous cases
    needs_review = [r for r in results if r["needs_claude_review"]]
    print(f"  [{brief_name}] {len(results) - len(needs_review)} verified mechanically, {len(needs_review)} need Claude review...")

    # Batch review in groups of ~20
    batch_size = 20
    for i in range(0, len(needs_review), batch_size):
        batch = needs_review[i:i+batch_size]
        reviews = _claude_review(batch, model)

        # Merge review results back
        for j, review in enumerate(reviews):
            if i + j < len(needs_review):
                item = needs_review[i + j]
                item["claude_review"] = review

    # Format report
    report = _format_report(brief_name, results)
    return (brief_name, report)


def _format_report(brief_name: str, results: list[dict]) -> str:
    """Format verification results into markdown."""
    lines = [f"### {brief_name} -- Cite-Check Report\n"]

    # Count errors by severity
    counts = {"Critical": 0, "Significant": 0, "Moderate": 0, "Minor": 0}
    errors = []
    for r in results:
        for issue in r.get("issues", []):
            sev = issue.get("severity", "Minor")
            if sev in counts:
                counts[sev] += 1
            errors.append((r["citation"], issue))
        review = r.get("claude_review", {})
        if review and not review.get("proposition_accurate", True):
            sev = review.get("severity", "Significant")
            if sev in counts:
                counts[sev] += 1
            errors.append((r["citation"], {
                "type": "proposition_inaccurate",
                "severity": sev,
                "detail": review.get("explanation", ""),
            }))

    total_errors = sum(counts.values())
    lines.append(f"**Summary**: {len(results)} citations checked, {total_errors} errors found "
                 f"({counts['Critical']} critical, {counts['Significant']} significant, "
                 f"{counts['Moderate']} moderate, {counts['Minor']} minor)\n")

    # Detail each citation
    for r in results:
        cite = r["citation"]
        issues = r.get("issues", [])
        review = r.get("claude_review", {})
        verified = r.get("verified_mechanically", [])

        if not issues and review.get("proposition_accurate", True):
            status = "VERIFIED"
        else:
            worst = "Minor"
            for issue in issues:
                sev = issue.get("severity", "Minor")
                if sev == "Critical":
                    worst = "Critical"
                elif sev == "Significant" and worst != "Critical":
                    worst = "Significant"
                elif sev == "Moderate" and worst not in ("Critical", "Significant"):
                    worst = "Moderate"
            if review and not review.get("proposition_accurate", True):
                rev_sev = review.get("severity", "Significant")
                if rev_sev == "Critical":
                    worst = "Critical"
                elif rev_sev == "Significant" and worst != "Critical":
                    worst = "Significant"
            status = worst

        lines.append(f"#### {cite}")
        lines.append(f"- **Cited for**: {r.get('proposition', 'N/A')}")
        lines.append(f"- **Status**: {status}")
        if r.get("authority_file"):
            lines.append(f"- **Authority file**: {r['authority_file']}")
        if verified:
            lines.append(f"- **Mechanically verified**: {', '.join(verified)}")
        for issue in issues:
            lines.append(f"- **{issue['severity']}**: {issue['detail']}")
        if review and review.get("explanation"):
            lines.append(f"- **Claude review**: {review['explanation']}")
        lines.append("")

    # Error summary table
    if errors:
        lines.append("#### Error Summary\n")
        lines.append("| # | Citation | Issue | Severity |")
        lines.append("|---|----------|-------|----------|")
        for i, (cite, issue) in enumerate(errors, 1):
            lines.append(f"| {i} | {cite} | {issue.get('detail', '')[:60]} | {issue.get('severity', '')} |")
        lines.append("")

    return "\n".join(lines)


def run(config: ProjectConfig):
    """Run cite-check on substantive briefs."""
    output_path = config.project_dir / "CITECHECK.md"

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"  Skipping (already exists): {output_path.name}")
        return

    txt_files = find_brief_texts(config.project_dir)
    if not txt_files:
        raise FileNotFoundError("No substantive brief .txt files found. Run the 'convert' step first.")

    auth_txts = list(config.authorities_dir.glob("*.txt"))
    if not auth_txts:
        raise FileNotFoundError("No authority .txt files found. Run 'westlaw' and 'process' steps first.")

    print(f"  Cite-checking {len(txt_files)} briefs against {len(auth_txts)} authorities")
    print(f"  Parallelism: {config.parallel_agents}")

    tasks = []
    for f in txt_files:
        tasks.append((
            f.name,
            f.read_text(errors="replace"),
            str(config.authorities_dir),
            config.claude_model,
        ))

    results = {}
    with ProcessPoolExecutor(max_workers=config.parallel_agents) as executor:
        futures = {
            executor.submit(_process_one_brief, task): task[0]
            for task in tasks
        }
        for future in as_completed(futures):
            brief_name = futures[future]
            try:
                name, result_text = future.result()
                results[name] = result_text
                print(f"  Completed: {name}")
            except Exception as e:
                print(f"  FAILED: {brief_name} -- {e}", file=sys.stderr)
                results[brief_name] = f"ERROR: {e}"

    sections = ["# Cite-Check Report\n"]
    for f in txt_files:
        name = f.name
        if name in results:
            sections.append(f"\n{results[name]}\n")

    output_path.write_text("\n".join(sections))
    print(f"  Written: {output_path.name} ({output_path.stat().st_size:,} bytes)")
