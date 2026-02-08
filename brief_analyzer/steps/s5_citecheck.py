"""Step 5: Cite-check briefs against authority texts.

Two-phase approach:
  5a. Claude extracts citation-proposition pairs from each brief (parallel).
  5b. For each cited authority, Claude verifies ALL propositions against the
      FULL text of the authority (parallel by authority).
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ..config import ProjectConfig
from ..utils.file_utils import classify_brief_type, find_brief_texts


# --- Phase A: Extract citation-proposition pairs ---

EXTRACT_PROMPT = """You are a legal citation extractor. Read this brief and extract every case citation with its context.

IMPORTANT: If the same case is cited multiple times for different propositions, different pin cites, or different quotations, output a SEPARATE entry for EACH use. This applies even when multiple cites appear in the same sentence or paragraph. For example, "Smith, 100 S.W.3d at 5 (holding X); id. at 12 (holding Y)" is TWO entries. Every distinct proposition-citation pairing gets its own entry.

## Brief Context

This is a{brief_type_article} {brief_type_label} filed by the {party}.{reply_guidance}

## Extraction Fields

For each citation instance, output a JSON object with these fields:
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
- purpose: one of "supporting", "extending", "critiquing", or "background" (see definitions below)
- argument_context: 1 sentence describing the legal argument this citation is part of

## Purpose Definitions

- **supporting**: standard affirmative cite -- the brief relies on the case's holding as-is to support its argument
- **extending**: the brief argues the case's holding should apply more broadly or to new facts beyond its original context
- **critiquing**: the brief argues this authority does NOT support the opposing party's position or is distinguishable
- **background**: cited for uncontested general propositions (standard of review, procedural rules, etc.)

Output ONLY a JSON array. No commentary, no markdown fencing, no reasoning. Your response must begin with [ and end with ].

BRIEF TEXT:

{brief_text}"""

REPLY_GUIDANCE = """

Reply-brief guidance for purpose classification:
- String cites following phrases like "the State relies on...", "none of these cases...", "these cases do not...", or "unlike in..." are likely "critiquing" -- the brief is arguing these authorities don't support the opposing side
- Citations that extend an opening-brief argument with new framing or applications are likely "extending"
- Citations reaffirming the opening brief's own authorities are likely "supporting"
"""


def _claude_env():
    """Return env dict with ANTHROPIC_API_KEY removed so claude uses the access token."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _parse_json_array(text: str, label: str = "") -> list[dict]:
    """Extract a JSON array from text that may contain markdown fences or reasoning preamble."""
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)

    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            if not parsed:
                print(f"    {label}: claude returned empty JSON array")
            return parsed
    except json.JSONDecodeError:
        pass

    # Find the outermost [...] in the response (handles reasoning preamble/postamble)
    start = text.find("[")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    print(f"    {label}: could not parse response as JSON ({len(text)} chars): {text[:200]}")
    return []


def _extract_pairs(brief_name: str, brief_text: str, model: str,
                    brief_type: dict | None = None) -> list[dict]:
    """Phase A: Use Claude to extract citation-proposition pairs."""
    if brief_type is None:
        brief_type = {"party": "unknown", "brief_type": "unknown"}

    # Build human-readable labels for the prompt
    type_labels = {
        "opening": "opening brief",
        "response": "response brief",
        "reply": "reply brief",
        "unknown": "brief",
    }
    brief_type_label = type_labels.get(brief_type["brief_type"], "brief")
    brief_type_article = "n" if brief_type_label[0] in "aeiou" else ""
    party = brief_type.get("party", "unknown")

    reply_guidance = REPLY_GUIDANCE if brief_type["brief_type"] == "reply" else ""

    prompt = EXTRACT_PROMPT.format(
        brief_text=brief_text,
        brief_type_article=brief_type_article,
        brief_type_label=brief_type_label,
        party=party,
        reply_guidance=reply_guidance,
    )

    cmd = ["claude", "--print", "--model", model]
    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=_claude_env())

    if result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip()
        print(f"  Extract failed for {brief_name}: {err_msg[:300]}", file=sys.stderr)
        return []

    text = result.stdout.strip()
    if not text:
        print(f"  {brief_name}: claude --print returned empty output")
        return []

    return _parse_json_array(text, brief_name)


# --- Authority file matching ---

def _find_authority_file(case_name: str, volume: str, reporter: str, page: str,
                         auth_files: dict[str, str]) -> tuple[str, str] | None:
    """Find the matching authority file by citation components.

    Returns (filename, text) or None.
    When multiple files share the same citation (companion cases),
    uses the case name to disambiguate.
    """
    cite_pattern = f"{volume} {reporter} {page}" if reporter != "WL" else f"{page}"

    # Extract name keywords for disambiguation
    name_words = []
    if case_name:
        for part in case_name.replace(" v. ", " v ").split(" v "):
            for w in part.strip().split():
                clean = w.rstrip(".,;:").lower()
                if len(clean) > 2 and clean not in ("state", "the", "united", "states"):
                    name_words.append(clean)

    # Collect all citation matches in filename
    cite_matches = [(fname, text) for fname, text in auth_files.items()
                    if cite_pattern in fname]

    if cite_matches:
        if len(cite_matches) == 1:
            return cite_matches[0]
        # Multiple files share this citation -- disambiguate by case name
        if name_words:
            for fname, text in cite_matches:
                fname_lower = fname.lower()
                if any(w in fname_lower for w in name_words):
                    return (fname, text)
        return cite_matches[0]

    # Try matching by case name (first party before "v.")
    if case_name:
        first_party = case_name.split(" v.")[0].split(" v ")[0].strip()
        if first_party:
            first_lower = first_party.lower().split()[-1]
            for fname, text in auth_files.items():
                if first_lower in fname.lower():
                    return (fname, text)

    # Try matching by citation in file content
    content_matches = []
    for fname, text in auth_files.items():
        header = text[:2000]
        if volume and reporter and page:
            if reporter == "WL":
                if f"WL {page}" in header:
                    content_matches.append((fname, text))
            elif f"{volume} {reporter} {page}" in header:
                content_matches.append((fname, text))

    if content_matches:
        if len(content_matches) == 1:
            return content_matches[0]
        if name_words:
            for fname, text in content_matches:
                fname_lower = fname.lower()
                if any(w in fname_lower for w in name_words):
                    return (fname, text)
        return content_matches[0]

    return None


# --- Phase B: Authority-centric Claude verification ---

VERIFY_PROMPT = """You are a legal cite-checker. Below is the FULL TEXT of a court opinion, followed by propositions from briefs that cite this case. Each proposition includes a "purpose" field that affects how you should evaluate it.

## Mechanical checks (apply to ALL purposes)

For every proposition, check:
1. Citation accuracy: reporter, pin cite, year, court -- do they match the opinion?
2. If a quotation is provided, is it verbatim? Check for omissions, alterations, or context changes.

## Purpose-specific evaluation

**For "supporting" citations** (standard affirmative cite):
- Does the authority support the stated proposition? Consider the full opinion.
- RELEVANCE CHECK: Does the authority address the legal issue described in argument_context? If the authority involves a different offense or legal area, set relevance to "analogous" and explain the gap. If the authority is on point, set relevance to "on_point". If the authority has no meaningful connection, set relevance to "off_point".
- Grade: "Verified" / "Minor" / "Moderate" / "Significant" / "Critical"

**For "extending" citations** (advocacy -- the brief argues the holding should apply more broadly):
- Describe what the case actually holds.
- Describe what the brief argues it should mean.
- Identify the gap the advocate needs to bridge.
- Grade: "Advocacy" -- this is NOT an error grade. This identifies an advocacy target.
- Still flag if the extension is unreasonable (e.g., the case holds the opposite) -- use "Critical" instead.

**For "critiquing" citations** (the brief argues this authority does NOT help the opposing side):
- Verify the critique, not the affirmative proposition. Does the case actually fail to address the topic the brief says it doesn't address?
- Grade: "Critique-Valid" (the critique is accurate -- the case does not address what the brief says it doesn't) or "Critique-Questionable" (the case does address the topic the brief claims it doesn't).

**For "background" citations** (uncontested general propositions):
- Light-touch check: is the stated proposition substantively correct?
- Grade: "Verified" or flag only if actually wrong.

## Output format

Output a JSON array with one object per proposition:
{{"index": <proposition number starting at 1>, "purpose": "supporting|extending|critiquing|background", "severity": "Verified|Minor|Moderate|Significant|Critical|Advocacy|Critique-Valid|Critique-Questionable", "quotation_accurate": true|false|null, "relevance": "on_point|analogous|off_point", "relevance_note": "<if analogous or off_point, explain what the case addresses vs. what the argument requires>", "explanation": "<1-2 sentences explaining your assessment>", "advocacy_gap": "<for extending only: what the case holds, what the brief argues, what gap must be bridged>"}}

For fields that don't apply to a given purpose, use null. For example, advocacy_gap is null for supporting citations; relevance is null for background citations.

Output ONLY the JSON array. No commentary, no markdown fencing, no reasoning. Your response must begin with [ and end with ].

=== AUTHORITY TEXT ===
{authority_text}

=== PROPOSITIONS TO VERIFY ===
{propositions}"""


def _verify_authority(authority_file: str, authority_text: str,
                      propositions: list[dict], model: str) -> list[dict]:
    """Send full authority text + all propositions to Claude for verification."""
    prop_lines = []
    for i, prop in enumerate(propositions, 1):
        prop_lines.append(f"--- Proposition {i} (from {prop['brief_name']}) ---")
        prop_lines.append(f"Citation as given: {prop.get('case_name', '?')}, "
                          f"{prop.get('volume', '')} {prop.get('reporter', '')} {prop.get('page', '')}")
        if prop.get("pin_cite"):
            prop_lines.append(f"Pin cite: {prop['pin_cite']}")
        purpose = prop.get("purpose", "supporting")
        prop_lines.append(f"Purpose: {purpose}")
        if prop.get("argument_context"):
            prop_lines.append(f"Argument context: {prop['argument_context']}")
        prop_lines.append(f"Proposition: {prop.get('proposition', '')}")
        if prop.get("quotation"):
            prop_lines.append(f'Quotation from brief: "{prop["quotation"]}"')
        prop_lines.append("")

    prompt = VERIFY_PROMPT.format(
        authority_text=authority_text,
        propositions="\n".join(prop_lines),
    )

    cmd = ["claude", "--print", "--model", model]
    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=_claude_env())

    if result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip()
        print(f"    {authority_file}: claude --print failed (exit {result.returncode}): {err_msg[:300]}")
        return []

    text = result.stdout.strip()
    if not text:
        print(f"    {authority_file}: claude --print returned empty output")
        return []

    return _parse_json_array(text, authority_file)


def _verify_one_authority(args: tuple, max_retries: int = 3) -> tuple[str, list[dict]]:
    """Wrapper for ProcessPoolExecutor with retry logic."""
    import time
    authority_file, authority_text, propositions, model = args
    for attempt in range(max_retries):
        results = _verify_authority(authority_file, authority_text, propositions, model)
        if results:
            return (authority_file, results)
        if attempt < max_retries - 1:
            wait = 30 * (attempt + 1)
            print(f"    {authority_file}: retrying in {wait}s (attempt {attempt + 2}/{max_retries})")
            time.sleep(wait)
    return (authority_file, results)


# --- Orchestration ---

def _group_by_authority(all_pairs: dict[str, list[dict]],
                        auth_files: dict[str, str]) -> dict[str | None, list[dict]]:
    """Group all citation-proposition pairs by authority file.

    all_pairs: {brief_name: [pair_dicts]}
    auth_files: {filename: text}

    Returns: {authority_filename: [proposition_dicts with brief_name added]}
    Pairs with no matching authority are collected under key None.
    """
    grouped = defaultdict(list)

    for brief_name, pairs in all_pairs.items():
        for pair in pairs:
            match = _find_authority_file(
                pair.get("case_name", ""),
                pair.get("volume", ""),
                pair.get("reporter", ""),
                pair.get("page", ""),
                auth_files,
            )
            prop = dict(pair)
            prop["brief_name"] = brief_name
            if match:
                fname, _ = match
                prop["authority_file"] = fname
                grouped[fname].append(prop)
            else:
                prop["authority_file"] = None
                grouped[None].append(prop)

    return grouped


def _format_report(brief_name: str, pairs: list[dict]) -> str:
    """Format verification results for one brief into markdown."""
    lines = [f"### {brief_name} -- Cite-Check Report\n"]

    # Categorize all pairs
    accuracy_issues = []     # supporting/background with real errors
    relevance_gaps = []      # supporting with analogous/off_point relevance
    advocacy_targets = []    # extending citations
    critiques = []           # critiquing citations
    verified_items = []      # clean supporting/background

    counts = {
        "Critical": 0, "Significant": 0, "Moderate": 0, "Minor": 0,
        "Verified": 0, "Advocacy": 0,
        "Critique-Valid": 0, "Critique-Questionable": 0, "Error": 0,
    }

    for pair in pairs:
        auth_file = pair.get("authority_file")
        citation = (f"{pair.get('case_name', '?')}, "
                    f"{pair.get('volume', '')} {pair.get('reporter', '')} {pair.get('page', '')}")
        proposition = pair.get("proposition", "")
        purpose = pair.get("purpose", "supporting")
        argument_context = pair.get("argument_context", "")
        verdict = pair.get("verdict")

        if verdict:
            severity = verdict.get("severity", "Error")
            explanation = verdict.get("explanation", "")
            quot_accurate = verdict.get("quotation_accurate")
            relevance = verdict.get("relevance")
            relevance_note = verdict.get("relevance_note", "")
            advocacy_gap = verdict.get("advocacy_gap", "")
        else:
            severity = "Error"
            explanation = "No verification result returned"
            quot_accurate = None
            relevance = None
            relevance_note = ""
            advocacy_gap = ""

        if auth_file is None:
            severity = "Critical"
            explanation = f"No authority file found for {citation}"

        if severity in counts:
            counts[severity] += 1

        entry = {
            "citation": citation,
            "proposition": proposition,
            "purpose": purpose,
            "argument_context": argument_context,
            "severity": severity,
            "explanation": explanation,
            "quot_accurate": quot_accurate,
            "auth_file": auth_file,
            "relevance": relevance,
            "relevance_note": relevance_note,
            "advocacy_gap": advocacy_gap,
        }

        # Route to appropriate section
        if severity == "Advocacy":
            advocacy_targets.append(entry)
        elif severity in ("Critique-Valid", "Critique-Questionable"):
            critiques.append(entry)
        elif relevance in ("analogous", "off_point") and severity == "Verified":
            relevance_gaps.append(entry)
        elif severity in ("Minor", "Moderate", "Significant", "Critical", "Error"):
            accuracy_issues.append(entry)
        else:
            verified_items.append(entry)

    # Summary line
    n_accuracy = len(accuracy_issues)
    n_relevance = len(relevance_gaps)
    n_advocacy = len(advocacy_targets)
    n_critiques = len(critiques)
    n_verified = len(verified_items)
    summary = (
        f"**Summary**: {len(pairs)} citations checked. "
        f"{n_accuracy} accuracy issue{'s' if n_accuracy != 1 else ''} "
        f"({counts['Critical']} critical, {counts['Significant']} significant, "
        f"{counts['Moderate']} moderate, {counts['Minor']} minor). "
        f"{n_advocacy} advocacy target{'s' if n_advocacy != 1 else ''}. "
        f"{n_relevance} relevance gap{'s' if n_relevance != 1 else ''}. "
        f"{n_critiques} critique{'s' if n_critiques != 1 else ''} checked."
    )
    if counts["Error"]:
        summary += f" {counts['Error']} FAILED VERIFICATION."
    lines.append(summary + "\n")

    # Section: Citation Accuracy (real errors only)
    if accuracy_issues:
        lines.append("#### Citation Accuracy\n")
        for e in accuracy_issues:
            lines.append(f"**{e['citation']}** -- {e['severity']}")
            lines.append(f"- **Cited for**: {e['proposition']}")
            if e['auth_file']:
                lines.append(f"- **Authority file**: {e['auth_file']}")
            lines.append(f"- **Assessment**: {e['explanation']}")
            if e['quot_accurate'] is False:
                lines.append(f"- **Quotation**: inaccurate")
            lines.append("")

    # Section: Relevance Gaps
    if relevance_gaps:
        lines.append("#### Relevance Gaps\n")
        for e in relevance_gaps:
            lines.append(f"**{e['citation']}** -- relevance: {e['relevance']}")
            lines.append(f"- **Cited for**: {e['proposition']}")
            if e['argument_context']:
                lines.append(f"- **Argument**: {e['argument_context']}")
            if e['relevance_note']:
                lines.append(f"- **Gap**: {e['relevance_note']}")
            if e['auth_file']:
                lines.append(f"- **Authority file**: {e['auth_file']}")
            lines.append("")

    # Section: Advocacy Targets
    if advocacy_targets:
        lines.append("#### Advocacy Targets\n")
        for e in advocacy_targets:
            lines.append(f"**{e['citation']}** -- Advocacy")
            lines.append(f"- **Cited for**: {e['proposition']}")
            if e['argument_context']:
                lines.append(f"- **Argument**: {e['argument_context']}")
            if e['advocacy_gap']:
                lines.append(f"- **Gap to bridge**: {e['advocacy_gap']}")
            if e['auth_file']:
                lines.append(f"- **Authority file**: {e['auth_file']}")
            lines.append("")

    # Section: Reply-Brief Critiques
    if critiques:
        lines.append("#### Reply-Brief Critiques\n")
        for e in critiques:
            lines.append(f"**{e['citation']}** -- {e['severity']}")
            lines.append(f"- **Cited for**: {e['proposition']}")
            if e['argument_context']:
                lines.append(f"- **Argument**: {e['argument_context']}")
            lines.append(f"- **Assessment**: {e['explanation']}")
            if e['auth_file']:
                lines.append(f"- **Authority file**: {e['auth_file']}")
            lines.append("")

    # Error Summary Table (accuracy errors only)
    if accuracy_issues:
        lines.append("#### Error Summary\n")
        lines.append("| # | Citation | Severity | Assessment |")
        lines.append("|---|----------|----------|------------|")
        for i, e in enumerate(accuracy_issues, 1):
            lines.append(f"| {i} | {e['citation']} | {e['severity']} | {e['explanation'][:80]} |")
        lines.append("")

    return "\n".join(lines)


def run(config: ProjectConfig):
    """Run cite-check on substantive briefs."""
    output_path = config.project_dir / "CITECHECK.md"

    if output_path.exists() and output_path.stat().st_size > 0 and not config.brief_filter:
        print(f"  Skipping (already exists): {output_path.name}")
        return

    txt_files = find_brief_texts(config.project_dir)
    if not txt_files:
        raise FileNotFoundError("No substantive brief .txt files found. Run the 'convert' step first.")

    if config.brief_filter:
        txt_files = [f for f in txt_files if config.brief_filter.lower() in f.name.lower()]
        if not txt_files:
            raise FileNotFoundError(f"No briefs matching '{config.brief_filter}'. Available: "
                                    + ", ".join(f.name for f in find_brief_texts(config.project_dir)))

    auth_txts = list(config.authorities_dir.glob("*.txt"))
    if not auth_txts:
        raise FileNotFoundError("No authority .txt files found. Run 'westlaw' and 'process' steps first.")

    # Load all authority texts once
    auth_files = {}
    for f in sorted(auth_txts):
        auth_files[f.name] = f.read_text(errors="replace")

    print(f"  Cite-checking {len(txt_files)} briefs against {len(auth_files)} authorities")

    # Classify each brief by type and party
    brief_types = {}
    for f in txt_files:
        bt = classify_brief_type(f.name)
        brief_types[f.name] = bt
        print(f"    {f.name}: {bt['brief_type']} ({bt['party']})")

    # Phase A: Extract citation-proposition pairs from each brief (parallel)
    print(f"  Phase A: Extracting citation-proposition pairs (model: {config.extraction_model})...")
    all_pairs = {}

    with ProcessPoolExecutor(max_workers=config.parallel_agents) as executor:
        futures = {}
        for f in txt_files:
            brief_text = f.read_text(errors="replace")
            bt = brief_types[f.name]
            future = executor.submit(_extract_pairs, f.name, brief_text, config.extraction_model, bt)
            futures[future] = f.name

        for future in as_completed(futures):
            brief_name = futures[future]
            try:
                pairs = future.result()
                all_pairs[brief_name] = pairs
                print(f"    {brief_name}: {len(pairs)} citations extracted")
            except Exception as e:
                print(f"    {brief_name}: FAILED -- {e}", file=sys.stderr)
                all_pairs[brief_name] = []

    total_pairs = sum(len(p) for p in all_pairs.values())
    print(f"  Total citations extracted: {total_pairs}")

    # Group by authority
    print("  Grouping propositions by authority...")
    grouped = _group_by_authority(all_pairs, auth_files)

    not_found = grouped.pop(None, [])
    if not_found:
        print(f"  {len(not_found)} citations have no matching authority file:")
        for prop in not_found:
            print(f"    - {prop.get('case_name', '?')}, "
                  f"{prop.get('volume', '')} {prop.get('reporter', '')} {prop.get('page', '')} "
                  f"(from {prop['brief_name']})")

    print(f"  {len(grouped)} authorities to verify")

    # Phase B: Verify each authority with full text (parallel)
    print(f"  Phase B: Verifying propositions against full authority texts (model: {config.verification_model})...")
    verdicts = {}

    tasks = []
    for auth_file, props in grouped.items():
        auth_text = auth_files[auth_file]
        tasks.append((auth_file, auth_text, props, config.verification_model))

    with ProcessPoolExecutor(max_workers=config.parallel_agents) as executor:
        futures = {
            executor.submit(_verify_one_authority, task): task[0]
            for task in tasks
        }
        for future in as_completed(futures):
            auth_file = futures[future]
            try:
                _, results = future.result()
                verdicts[auth_file] = results
                n_issues = sum(1 for r in results if r.get("severity") not in ("Verified", None))
                print(f"    {auth_file}: {len(results)} propositions, {n_issues} issues")
            except Exception as e:
                print(f"    {auth_file}: FAILED -- {e}", file=sys.stderr)
                verdicts[auth_file] = []

    # Retry any authorities that returned no results
    failed = [t for t in tasks if not verdicts.get(t[0])]
    if failed:
        print(f"  Retrying {len(failed)} failed verification(s)...")
        with ProcessPoolExecutor(max_workers=config.parallel_agents) as executor:
            futures = {
                executor.submit(_verify_one_authority, task): task[0]
                for task in failed
            }
            for future in as_completed(futures):
                auth_file = futures[future]
                try:
                    _, results = future.result()
                    verdicts[auth_file] = results
                    n_issues = sum(1 for r in results if r.get("severity") not in ("Verified", None))
                    print(f"    {auth_file}: {len(results)} propositions, {n_issues} issues")
                except Exception as e:
                    print(f"    {auth_file}: RETRY FAILED -- {e}", file=sys.stderr)

    # Match verdicts back to pairs by index
    for auth_file, props in grouped.items():
        auth_verdicts = verdicts.get(auth_file, [])
        if auth_verdicts:
            for verdict in auth_verdicts:
                idx = verdict.get("index", 0) - 1  # 1-indexed to 0-indexed
                if 0 <= idx < len(props):
                    props[idx]["verdict"] = verdict
        else:
            # Verification failed — mark all propositions for this authority
            for prop in props:
                prop["verdict"] = {
                    "severity": "Error",
                    "explanation": f"Verification failed for {auth_file} — Claude returned no results",
                    "quotation_accurate": None,
                }

    # Mark not-found citations
    for prop in not_found:
        prop["verdict"] = {
            "severity": "Critical",
            "explanation": "No authority file found",
            "quotation_accurate": None,
        }

    # Format report per brief
    sections = ["# Cite-Check Report\n"]
    for f in txt_files:
        brief_name = f.name
        brief_pairs = []
        for auth_file, props in grouped.items():
            brief_pairs.extend(p for p in props if p["brief_name"] == brief_name)
        brief_pairs.extend(p for p in not_found if p["brief_name"] == brief_name)

        if brief_pairs:
            report = _format_report(brief_name, brief_pairs)
            sections.append(f"\n{report}\n")

    output_path.write_text("\n".join(sections))
    print(f"  Written: {output_path.name} ({output_path.stat().st_size:,} bytes)")

    # Warn about any verifications that returned no results
    failed_auths = [f for f, v in verdicts.items() if not v and grouped.get(f)]
    if failed_auths:
        print(f"\n  WARNING: {len(failed_auths)} authorities failed verification (marked as Error in report):")
        for f in failed_auths:
            print(f"    - {f}")
