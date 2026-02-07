"""Step 5: Verify that all authorities listed in AUTHORITIES.md have been downloaded.

Parses AUTHORITIES.md, matches each case citation to a file in authorities/,
and reports any missing or uncertain matches so the user can find them
before cite-checking begins.
"""

import re
import sys
import time
from pathlib import Path

from ..config import ProjectConfig


# Parse case entries from AUTHORITIES.md -- lines starting with **CaseName, Citation**
# Examples:
#   **Wood v. Clemons, 89 F.3d 922 (1st Cir. 1996)**
#   **Haywood v. State, No. 01-13-00994-CR, 2014 WL 7131176 (Tex. App.—Houston [1st Dist.] Dec. 11, 2014, pet. ref'd)**
CASE_ENTRY_RE = re.compile(
    r"^\*\*(.+?)\*\*$", re.MULTILINE
)

# Extract volume/reporter/page from a citation string
CITE_RE = re.compile(
    r"(\d+)\s+"
    r"(S\.W\.(?:2d|3d)|F\.(?:2d|3d|4th)|F\.\s*App'x|F\.\s*Supp\.(?:\s*2d)?|"
    r"U\.S\.|A\.2d|N\.E\.2d|P\.2d|P\.3d|Tex\.)"
    r"\s+(\d+)"
)

WL_CITE_RE = re.compile(r"(\d{4})\s+WL\s+(\d+)")


# Generic first parties that appear in many cases -- prefer second party for matching
GENERIC_PARTIES = {
    "united states", "people", "state", "commonwealth", "com", "florida",
    "kansas", "minnesota", "texas", "illinois", "california",
}

# Words to strip from the end of party names (not useful for matching)
PARTY_NOISE_WORDS = {"no", "inc", "co", "corp", "ltd", "dist", "et", "al"}


def _extract_match_names(case_name: str) -> list[str]:
    """Extract useful name tokens from a case name for file matching.

    Returns a list of names to try, most specific first.
    For 'United States v. Spriggs' -> ['spriggs']
    For 'Safford Unified School District No. 1 v. Redding' -> ['redding', 'safford']
    For 'Wood v. Clemons' -> ['wood', 'clemons']
    """
    if " v. " in case_name:
        parts = case_name.split(" v. ", 1)
    elif " v " in case_name:
        parts = case_name.split(" v ", 1)
    else:
        parts = [case_name]

    first_party = parts[0].strip()
    second_party = parts[1].strip() if len(parts) > 1 else ""

    names = []

    # Determine if first party is generic
    first_lower = first_party.lower().rstrip(".,")
    is_generic = first_lower in GENERIC_PARTIES

    def _best_word(party: str) -> str:
        """Get the most distinctive word from a party name."""
        words = party.split()
        # Walk backwards, skip noise words and numbers
        for w in reversed(words):
            clean = w.rstrip(".,;:").lower()
            if clean.isdigit() or len(clean) <= 1 or clean in PARTY_NOISE_WORDS:
                continue
            return clean
        # Fallback: first substantive word
        for w in words:
            clean = w.rstrip(".,;:").lower()
            if len(clean) > 1 and not clean.isdigit():
                return clean
        return ""

    if is_generic and second_party:
        # For "United States v. Spriggs", try Spriggs first
        sp = _best_word(second_party)
        if sp:
            names.append(sp)
        fp = _best_word(first_party)
        if fp:
            names.append(fp)
    else:
        # For normal cases, try first party, then second
        fp = _best_word(first_party)
        if fp:
            names.append(fp)
        if second_party:
            sp = _best_word(second_party)
            if sp:
                names.append(sp)

    return names


def _parse_authorities_md(text: str) -> list[dict]:
    """Parse AUTHORITIES.md and extract case citation info.

    Returns list of dicts with: full_entry, case_name, volume, reporter, page,
    wl_year, wl_number, match_names, cited_by, proposition.
    """
    cases = []
    in_cases_section = False
    current_case = None

    for line in text.split("\n"):
        if line.strip() == "## Cases":
            in_cases_section = True
            continue
        if line.startswith("## ") and in_cases_section:
            break  # hit next section
        if not in_cases_section:
            continue

        stripped = line.strip()

        # "- Cited by:" line belongs to the current case
        if stripped.startswith("- Cited by:") and current_case:
            current_case["cited_by"] = stripped[len("- Cited by:"):].strip()
            continue

        # "- Proposition:" line belongs to the current case
        if stripped.startswith("- Proposition:") and current_case:
            current_case["proposition"] = stripped[len("- Proposition:"):].strip()
            continue

        m = CASE_ENTRY_RE.match(stripped)
        if not m:
            continue

        entry_text = m.group(1)
        current_case = {
            "full_entry": entry_text,
            "case_name": "",
            "volume": "",
            "reporter": "",
            "page": "",
            "wl_year": "",
            "wl_number": "",
            "docket_number": "",
            "match_names": [],
            "cited_by": "",
            "proposition": "",
        }

        # Extract case name (everything before first comma that precedes a number)
        name_match = re.match(r"(.+?),\s*(?:No\.|[0-9])", entry_text)
        if name_match:
            current_case["case_name"] = name_match.group(1).strip()
        else:
            # Fallback: everything before the first number sequence
            name_match2 = re.match(r"(.+?),\s", entry_text)
            if name_match2:
                current_case["case_name"] = name_match2.group(1).strip()

        # Extract matching names (handles generic parties, noise words, etc.)
        current_case["match_names"] = _extract_match_names(current_case["case_name"])

        # Extract reporter citation
        cite_m = CITE_RE.search(entry_text)
        if cite_m:
            current_case["volume"] = cite_m.group(1)
            current_case["reporter"] = cite_m.group(2)
            current_case["page"] = cite_m.group(3)

        # Extract WL citation
        wl_m = WL_CITE_RE.search(entry_text)
        if wl_m:
            current_case["wl_year"] = wl_m.group(1)
            current_case["wl_number"] = wl_m.group(2)

        # Extract docket number (e.g., "No. PD-0230-24", "No. 01-13-00994-CR")
        docket_m = re.search(r"No\.\s+([\w-]+)", entry_text)
        if docket_m:
            current_case["docket_number"] = docket_m.group(1)

        cases.append(current_case)

    return cases


def _match_authority(case: dict, auth_files: dict[str, str]) -> dict:
    """Try to match a case entry to an authority file.

    Returns dict with: status (found/uncertain/missing), file, match_method.
    Strategies ordered from most to least reliable:
      1. Citation in filename
      2. WL number in filename
      3. Citation in full file content
      4. WL cite in full file content
      5. Both party names in filename (name-confirmed)
      6. Primary name in filename with single match (uncertain)
    """
    volume = case["volume"]
    reporter = case["reporter"]
    page = case["page"]
    wl_year = case["wl_year"]
    wl_number = case["wl_number"]
    match_names = case.get("match_names", [])

    # Strategy 1: exact volume/reporter/page in filename
    if volume and reporter and page:
        cite_str = f"{volume} {reporter} {page}"
        cite_hits = [fname for fname in auth_files if cite_str in fname]
        if len(cite_hits) == 1:
            return {"status": "found", "file": cite_hits[0], "match_method": "cite_in_filename"}
        if len(cite_hits) > 1:
            # Multiple files share this citation (companion cases) — disambiguate by name
            for fname in cite_hits:
                fname_lower = fname.lower()
                if any(n in fname_lower for n in match_names):
                    return {"status": "found", "file": fname, "match_method": "cite_in_filename (disambiguated)"}
            # Fallback to first match
            return {"status": "found", "file": cite_hits[0], "match_method": "cite_in_filename"}

    # Strategy 2: WL number in filename
    if wl_number:
        for fname in auth_files:
            if wl_number in fname:
                return {"status": "found", "file": fname, "match_method": "wl_in_filename"}

    # Strategy 3: volume/reporter/page in full file content
    # Westlaw files often have the parallel cite far from the header
    if volume and reporter and page:
        cite_str = f"{volume} {reporter} {page}"
        cite_variants = [cite_str]
        if "U.S." in reporter:
            cite_variants.append(cite_str.replace("U.S.", "U. S."))
        content_hits = []
        for fname, text in auth_files.items():
            for variant in cite_variants:
                if variant in text:
                    content_hits.append(fname)
                    break
        if len(content_hits) == 1:
            return {"status": "found", "file": content_hits[0], "match_method": "cite_in_content"}
        if len(content_hits) > 1:
            # Disambiguate by case name
            for fname in content_hits:
                fname_lower = fname.lower()
                if any(n in fname_lower for n in match_names):
                    return {"status": "found", "file": fname, "match_method": "cite_in_content (disambiguated)"}
            return {"status": "found", "file": content_hits[0], "match_method": "cite_in_content"}

    # Strategy 4: WL cite in full file content
    if wl_year and wl_number:
        wl_str = f"{wl_year} WL {wl_number}"
        for fname, text in auth_files.items():
            if wl_str in text:
                return {"status": "found", "file": fname, "match_method": "wl_in_content"}

    # Strategy 4b: docket number in file content
    docket = case.get("docket_number", "")
    if docket:
        for fname, text in auth_files.items():
            if docket in text:
                return {"status": "found", "file": fname, "match_method": "docket_in_content"}

    # Strategy 4c: raw citation string in file content
    # For reporters not in our regex (S.W., Port., Hill, etc.), extract any
    # "volume reporter page" pattern from the entry and search file content.
    if not volume:
        raw_cites = re.findall(r'\b(\d+\s+[A-Za-z][A-Za-z. \']+\s+\d+)\b',
                               case["full_entry"])
        for raw_cite in raw_cites:
            raw_cite = raw_cite.strip()
            if len(raw_cite) < 5:
                continue
            hits = [fname for fname, text in auth_files.items()
                    if raw_cite in text[:2000]]
            if len(hits) == 1:
                return {"status": "found", "file": hits[0],
                        "match_method": f"raw_cite_in_content ({raw_cite})"}

    # Strategy 5: name matching in file content (handles misspellings in brief)
    # Search the first 2000 chars of each file for party names.
    # Uses prefix matching (min 4 chars) to handle common misspellings
    # like Gonzalez/Gonzales, Lightsey/Lightsy, etc.
    if match_names:
        for name in match_names:
            if name in GENERIC_PARTIES:
                continue
            # Use prefix (drop last 1-2 chars) to handle spelling variants
            prefix = name[:max(4, len(name) - 2)] if len(name) > 4 else name
            content_name_hits = []
            for fname, text in auth_files.items():
                header = text[:2000].lower()
                if prefix in header:
                    content_name_hits.append(fname)
            if len(content_name_hits) == 1:
                return {"status": "found", "file": content_name_hits[0],
                        "match_method": f"name_in_content ({name})"}
            if len(content_name_hits) > 1:
                # Try narrowing with other party name
                if len(match_names) > 1:
                    other = [n for n in match_names if n != name and n not in GENERIC_PARTIES]
                    for oname in other:
                        both = [f for f in content_name_hits if oname in auth_files[f][:2000].lower()]
                        if len(both) == 1:
                            return {"status": "found", "file": both[0],
                                    "match_method": f"both_names_in_content ({name}, {oname})"}
                # Try narrowing by page number in file content
                if page:
                    page_hits = [f for f in content_name_hits
                                 if re.search(r'\b' + re.escape(page) + r'\b',
                                              auth_files[f][:2000])]
                    if len(page_hits) == 1:
                        return {"status": "found", "file": page_hits[0],
                                "match_method": f"name_and_page_in_content ({name}, p.{page})"}

    # Strategy 6: name matching in filename
    if not match_names:
        return {"status": "missing", "file": None, "match_method": None}

    primary_name = match_names[0]  # most distinctive name
    secondary_name = match_names[1] if len(match_names) > 1 else None

    # Find all files matching the primary name
    primary_matches = []
    for fname in auth_files:
        fname_lower = fname.lower()
        if primary_name in fname_lower:
            primary_matches.append(fname)

    if not primary_matches:
        # Try secondary name
        if secondary_name:
            for fname in auth_files:
                if secondary_name in fname.lower():
                    primary_matches.append(fname)
            if len(primary_matches) == 1:
                return {"status": "uncertain", "file": primary_matches[0],
                        "match_method": f"secondary_name ({secondary_name})"}

        return {"status": "missing", "file": None, "match_method": None}

    # If primary name gives exactly one match, that's good but uncertain
    if len(primary_matches) == 1:
        return {"status": "uncertain", "file": primary_matches[0],
                "match_method": f"name ({primary_name})"}

    # Multiple matches on primary -- narrow with secondary
    if secondary_name:
        both_matches = [f for f in primary_matches if secondary_name in f.lower()]
        if len(both_matches) == 1:
            return {"status": "found", "file": both_matches[0],
                    "match_method": f"both_parties ({primary_name}, {secondary_name})"}
        elif both_matches:
            return {"status": "uncertain", "file": both_matches[0],
                    "match_method": f"both_parties ({primary_name}, {secondary_name}, {len(both_matches)} candidates)"}

    # Multiple matches, no secondary narrowing -- uncertain, pick first
    return {"status": "uncertain", "file": primary_matches[0],
            "match_method": f"name ({primary_name}, {len(primary_matches)} candidates)"}


def _wait_for_missing(missing: list, config: ProjectConfig, timeout: int = 300):
    """Wait for the user to add missing authority files.

    Interactive: prompts for Enter.
    Non-interactive: watches authorities/ for new .txt files.
    """
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()

    if is_tty:
        input("\n  Press Enter after adding the missing files (or Enter to skip)...")
        return

    # Non-interactive: watch for new .txt files in authorities/
    auth_dir = config.authorities_dir
    snapshot = set(auth_dir.glob("*.txt"))
    print(f"\n  Watching {auth_dir} for new .txt files (timeout {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        current = set(auth_dir.glob("*.txt"))
        new_files = current - snapshot
        if new_files:
            names = [f.name[:60] for f in new_files]
            print(f"  Detected {len(new_files)} new file(s): {names}")
            time.sleep(2)
            return
    print(f"  Timeout waiting for missing authorities. Proceeding anyway.")


def run(config: ProjectConfig):
    """Verify all authorities in AUTHORITIES.md have matching files."""
    auth_md = config.project_dir / "AUTHORITIES.md"
    if not auth_md.exists():
        raise FileNotFoundError("AUTHORITIES.md not found. Run the 'authorities' step first.")

    auth_dir = config.authorities_dir
    txt_files = sorted(auth_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError("No authority .txt files found. Run 'westlaw' and 'process' steps first.")

    # Load all authority texts (read once)
    auth_files = {}
    for f in txt_files:
        auth_files[f.name] = f.read_text(errors="replace")

    # Parse AUTHORITIES.md
    md_text = auth_md.read_text(errors="replace")
    cases = _parse_authorities_md(md_text)

    if not cases:
        print("  No case entries found in AUTHORITIES.md")
        return

    print(f"  Checking {len(cases)} cases against {len(auth_files)} authority files...")

    found = []
    uncertain = []
    missing = []

    for case in cases:
        result = _match_authority(case, auth_files)
        result["case"] = case
        if result["status"] == "found":
            found.append(result)
        elif result["status"] == "uncertain":
            uncertain.append(result)
        else:
            missing.append(result)

    # Report
    print(f"\n  Results: {len(found)} found, {len(uncertain)} uncertain, {len(missing)} missing\n")

    if uncertain:
        print("  UNCERTAIN MATCHES (matched by name only, not citation):")
        print("  " + "-" * 70)
        for r in uncertain:
            c = r["case"]
            cite = f"{c['volume']} {c['reporter']} {c['page']}" if c["volume"] else f"{c['wl_year']} WL {c['wl_number']}"
            print(f"    {c['case_name']}, {cite}")
            print(f"      -> {r['file']}")
            print(f"      Method: {r['match_method']}")
        print()

    if missing:
        print("  MISSING AUTHORITIES (no matching file found):")
        print("  " + "-" * 70)
        for r in missing:
            c = r["case"]
            print(f"    {c['full_entry']}")
            if c.get("cited_by"):
                print(f"      Cited by: {c['cited_by']}")
        print()

        # Write missing authorities.txt with full citation and brief info
        missing_path = config.project_dir / "missing authorities.txt"
        lines = []
        lines.append(f"{len(missing)} authorities cited in the briefs have no matching text file.")
        lines.append("")
        for r in missing:
            c = r["case"]
            lines.append(c["full_entry"])
            if c.get("cited_by"):
                lines.append(f"  Cited by: {c['cited_by']}")
            if c.get("proposition"):
                lines.append(f"  Proposition: {c['proposition']}")
            lines.append("")
        missing_path.write_text("\n".join(lines))
        print(f"  Wrote: {missing_path.name}")

        print(f"\n  {len(missing)} authorities are missing from authorities/.")
        print("  The ci() search included these citations but Westlaw did not return them.")
        print("  This usually means the citation in the brief is wrong.")
        print(f"  Please find the missing authorities and place .txt files in:")
        print(f"    {config.authorities_dir}")

        # Wait for user to add files, then re-verify
        _wait_for_missing(missing, config)

        # Re-scan and re-verify
        auth_files = {}
        for f in config.authorities_dir.glob("*.txt"):
            auth_files[f.name] = f.read_text(errors="replace")
        still_missing = []
        for r in missing:
            result = _match_authority(r["case"], auth_files)
            if result["status"] == "missing":
                still_missing.append(r)
            else:
                result["case"] = r["case"]
                found.append(result)
                print(f"    Found: {r['case']['case_name']}")

        if still_missing:
            names = [r["case"]["case_name"] for r in still_missing]
            print(f"\n  Still missing {len(still_missing)}: {', '.join(names)}")
            print("  Proceeding without them -- cite-check will note these as unavailable.")

        missing = still_missing

    if uncertain:
        print(f"  {len(uncertain)} authorities matched by name only.")
        print("  These may be correct but could not be confirmed by citation.")
        print("  Proceeding to cite-check; review uncertain matches if issues arise.")

    print(f"  All {len(found) + len(uncertain)} authorities accounted for.")
