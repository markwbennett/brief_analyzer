"""Step 4: Process downloaded authorities -- RTF to text, rename, organize.

Naming convention: full legal citation as it appears in AUTHORITIES.md.
  e.g. "Ramos v. Louisiana, 590 U.S. 83 (2020).txt"

When the brief's citation is incorrect (wrong name spelling, wrong volume),
the file is named with the CORRECT citation from the RTF/Westlaw header,
and a symlink prefixed with "-" is created for the brief's erroneous citation.
  e.g. file:    "Gonzales v. State, 270 S.W.3d 282 (Tex. App.--Amarillo 2008, no pet.).txt"
       symlink: "-Gonzalez v. State, 720 S.W.3d 282 (Tex. App.--Amarillo 2008, no pet.).txt"

AUTHORITIES.md is the canonical source for how briefs cite each case.
The RTF header (Westlaw metadata) is the source of truth for the correct citation.
"""

import os
import re
import subprocess
from pathlib import Path

from ..config import ProjectConfig
from ..utils.file_utils import sanitize_filename


# --- RTF header citation extraction ---

# Matches: "Name v. Name, 123 Reporter 456" in RTF content
_RTF_REPORTED_RE = re.compile(
    r'([A-Z][A-Za-z\s.,\'-]+v\.\s+[A-Za-z\s.,\'-]+,'
    r'\s+(\d+)\s+([A-Za-z][A-Za-z.\s\d]+?)\s+(\d+))'
)

# Matches: "In re Name, ..." or "Ex parte Name, ..."
_RTF_INRE_REPORTED_RE = re.compile(
    r'((?:In re|Ex parte)\s+[A-Za-z\s.,\'-]+,'
    r'\s+(\d+)\s+([A-Za-z][A-Za-z.\s\d]+?)\s+(\d+))'
)


def _parse_rtf_header_cite(rtf_path: Path) -> tuple[str, str] | None:
    """Extract case name and citation from the Westlaw RTF header.

    Returns (case_name, cite_part) e.g. ("Gonzales v. State", "270 S.W.3d 282")
    or None if no citation found.
    """
    try:
        with open(rtf_path, "r", errors="replace") as f:
            content = f.read(10000)
    except OSError:
        return None

    for pattern in [_RTF_REPORTED_RE, _RTF_INRE_REPORTED_RE]:
        m = pattern.search(content[:8000])
        if m:
            full_match = m.group(1)
            name_cite = re.sub(r'\\[a-z]+\d*\s?', '', full_match)
            name_cite = re.sub(r'[{}]', '', name_cite)
            name_cite = re.sub(r'\s+', ' ', name_cite).strip()

            parts = re.split(r',\s+(?=\d)', name_cite, maxsplit=1)
            if len(parts) == 2:
                return (parts[0].strip(), parts[1].strip())

    return None


def _parse_authorities_md(auth_md_path: Path) -> list[str]:
    """Extract full citations from AUTHORITIES.md bold lines.

    Returns list of citation strings, e.g.:
      "Ramos v. Louisiana, 590 U.S. 83 (2020)"
      "Montalvo v. State, 846 S.W.2d 133 (Tex. App.—Austin 1993, no pet.)"
    """
    if not auth_md_path.exists():
        return []

    text = auth_md_path.read_text(errors="replace")
    # Match **Full Citation** lines
    citations = re.findall(r'\*\*(.+?)\*\*', text)
    # Filter to actual case citations (must contain "v." or "In re" or "Ex parte")
    return [c.strip() for c in citations
            if " v. " in c or "In re " in c or "Ex parte " in c]


def _normalize_name(name: str) -> str:
    """Normalize a case name for fuzzy matching.

    Lowercases, strips punctuation, collapses whitespace.
    """
    s = name.lower()
    # Replace hyphens with spaces (so "luz-Torres" -> "luz torres", not "luztorres")
    s = s.replace('-', ' ')
    s = re.sub(r'[.,\']', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _extract_key_words(name: str) -> set[str]:
    """Extract meaningful words from a case name for matching.

    Strips common filler words that differ between Westlaw and brief style.
    """
    stop = {"v", "the", "of", "at", "and", "in", "re", "ex", "parte",
            "no", "state", "states", "united", "texas"}
    words = set()
    for w in _normalize_name(name).split():
        if w not in stop and len(w) > 2:
            words.add(w)
    return words


def _match_rtf_to_citation(rtf_path: Path, citations: list[str],
                            rtf_content: str = "") -> str | None:
    """Match an RTF file to its AUTHORITIES.md citation by case name.

    Uses the RTF filename (e.g. "34 - Ramos v Louisiana.rtf") to find
    the matching citation entry. For ambiguous matches (multiple Smith v. State),
    uses RTF text content to disambiguate by citation.
    """
    stem = rtf_path.stem
    # Strip leading number prefix: "34 - "
    stem = re.sub(r'^\d+\s*-\s*', '', stem)
    rtf_name = _normalize_name(stem)
    rtf_words = _extract_key_words(stem)

    candidates = []

    for cite in citations:
        # Extract case name portion (before the first comma + digit/No./__/WL)
        case_part = re.split(r',\s+(?:\d|No\.|__)', cite, maxsplit=1)[0]
        cite_name = _normalize_name(case_part)

        # Exact match after normalization
        if rtf_name == cite_name:
            candidates.append((cite, 100))
            continue

        # Split on "v" to get party names
        rtf_parts = rtf_name.split(" v ")
        cite_parts = cite_name.split(" v ")

        # Key-word overlap
        cite_words = _extract_key_words(case_part)
        overlap = rtf_words & cite_words if rtf_words and cite_words else set()

        matched = False
        if len(rtf_parts) == 2 and len(cite_parts) == 2:
            # Compare first party's last word (the surname)
            rtf_p1 = rtf_parts[0].split()[-1] if rtf_parts[0].split() else ""
            cite_p1 = cite_parts[0].split()[-1] if cite_parts[0].split() else ""
            # Compare second party's first word
            rtf_p2 = rtf_parts[1].split()[0] if rtf_parts[1].split() else ""
            cite_p2 = cite_parts[1].split()[0] if cite_parts[1].split() else ""

            # Match if first party surname matches
            if rtf_p1 and rtf_p1 == cite_p1:
                # Second party: "us" matches "united" (Kotteakos v US),
                # "state" matches "state", abbreviations match first letters
                p2_match = (rtf_p2 == cite_p2
                            or cite_p2.startswith(rtf_p2)
                            or rtf_p2.startswith(cite_p2))
                if p2_match:
                    matched = True

        # Handle "In re" / "Ex parte"
        for prefix in ("in re ", "ex parte "):
            if rtf_name.startswith(prefix) and cite_name.startswith(prefix):
                rtf_first = rtf_name[len(prefix):].split()[0] if rtf_name[len(prefix):].split() else ""
                cite_first = cite_name[len(prefix):].split()[0] if cite_name[len(prefix):].split() else ""
                if rtf_first and rtf_first == cite_first:
                    matched = True

        # Also match by keyword overlap for names with unusual structure
        # (e.g. "de la Luz Torres" vs "De la luz-Torres",
        #  "Kotteakos v US" vs "Kotteakos v. United States",
        #  "Gonzales" vs "Gonzalez")
        if not matched:
            # Try with first-party surname prefix match (handles spelling variants)
            if len(rtf_parts) == 2 and len(cite_parts) == 2:
                rtf_p1 = rtf_parts[0].split()[-1] if rtf_parts[0].split() else ""
                cite_p1 = cite_parts[0].split()[-1] if cite_parts[0].split() else ""
                # Prefix match: "gonzales" matches "gonzalez" (off by one letter)
                min_len = min(len(rtf_p1), len(cite_p1))
                if min_len >= 4 and rtf_p1[:min_len-1] == cite_p1[:min_len-1]:
                    matched = True

            # Keyword overlap fallback
            if not matched and len(overlap) >= 2:
                matched = True

        if matched:
            candidates.append((cite, len(overlap)))

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0][0]

    # Multiple candidates — try to disambiguate
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)

    # If top score is unique, use it
    if candidates[0][1] > candidates[1][1]:
        return candidates[0][0]

    # Disambiguate using RTF text content: check which citation appears in text
    if rtf_content:
        header = rtf_content[:5000]
        for cite, _ in candidates:
            # Extract reporter citation (e.g. "868 S.W.2d 337" or "2019 WL 938276")
            cite_m = re.search(r'(\d+)\s+(S\.W\.(?:2d|3d)|U\.S\.|WL)\s+(\d+)', cite)
            if cite_m:
                cite_str = f"{cite_m.group(1)} {cite_m.group(2)} {cite_m.group(3)}"
                if cite_str in header:
                    return cite

        # Looser match: reporter + page only (handles volume typos in briefs,
        # e.g. brief says "720 S.W.3d 282" but correct cite is "270 S.W.3d 282")
        for cite, _ in candidates:
            cite_m = re.search(r'\d+\s+(S\.W\.(?:2d|3d)|U\.S\.|WL)\s+(\d+)', cite)
            if cite_m:
                page_pattern = f"{cite_m.group(1)} {cite_m.group(2)}"
                if page_pattern in header:
                    return cite

    # Fall back to first candidate
    return candidates[0][0]


def _split_citation(full_cite: str) -> tuple[str, str, str]:
    """Split a full AUTHORITIES.md citation into (case_name, cite_part, parenthetical).

    "Gonzalez v. State, 720 S.W.3d 282 (Tex. App.—Amarillo 2008, no pet.)"
    -> ("Gonzalez v. State", "720 S.W.3d 282", "(Tex. App.—Amarillo 2008, no pet.)")
    """
    # Find the first opening paren that's the parenthetical (not part of cite)
    paren_m = re.search(r'\s+(\([^)]+\)(?:\s*\([^)]+\))*)\s*$', full_cite)
    if paren_m:
        before_paren = full_cite[:paren_m.start()].strip()
        parenthetical = paren_m.group(1)
    else:
        before_paren = full_cite
        parenthetical = ""

    # Split name from cite at first comma + digit/No./__
    parts = re.split(r',\s+(?=\d|No\.|__)', before_paren, maxsplit=1)
    if len(parts) == 2:
        return (parts[0].strip(), parts[1].strip(), parenthetical)
    return (before_paren, "", parenthetical)


def _check_cite_discrepancy(brief_cite: str, rtf_path: Path) -> str | None:
    """Compare the brief's citation against the RTF header's correct citation.

    If the brief has an error (wrong name spelling, wrong volume), returns the
    corrected full citation (correct name + cite with brief's parenthetical).
    Returns None if no discrepancy or can't determine.
    """
    rtf_header = _parse_rtf_header_cite(rtf_path)
    if not rtf_header:
        return None

    rtf_name, rtf_cite = rtf_header
    brief_name, brief_cite_part, brief_paren = _split_citation(brief_cite)

    if not brief_cite_part:
        return None

    # Normalize for comparison
    def norm(s):
        return re.sub(r'\s+', ' ', s.lower().strip())

    name_matches = norm(rtf_name) == norm(brief_name)
    cite_matches = norm(rtf_cite) == norm(brief_cite_part)

    if name_matches and cite_matches:
        return None  # No discrepancy

    # Build corrected citation: RTF's correct name + cite, brief's parenthetical
    corrected = f"{rtf_name}, {rtf_cite}"
    if brief_paren:
        corrected += f" {brief_paren}"
    return corrected


def run(config: ProjectConfig):
    """Convert RTFs to text, rename using citations from AUTHORITIES.md."""
    auth_dir = config.authorities_dir
    rtf_dir = config.rtf_dir
    rtf_dir.mkdir(exist_ok=True)

    # Parse AUTHORITIES.md for canonical citation names
    auth_md_path = config.project_dir / "AUTHORITIES.md"
    citations = _parse_authorities_md(auth_md_path)
    if not citations:
        print("  No citations found in AUTHORITIES.md. Run the 'authorities' step first.")
        return
    print(f"  Loaded {len(citations)} citations from AUTHORITIES.md")

    # Find RTF files
    rtfs = sorted(rtf_dir.glob("*.rtf")) + sorted(rtf_dir.glob("*.RTF"))
    rtfs = [r for r in rtfs if not r.name.startswith("~")]
    if not rtfs:
        print("  No RTF files found in authorities/rtf/. Nothing to process.")
        return

    print(f"  Found {len(rtfs)} RTF files to process.")

    converted = 0
    renamed = 0
    skipped = 0
    symlinks = 0
    unmatched = []

    for rtf_path in rtfs:
        # Convert RTF to text using textutil (macOS).
        txt_in_rtf_dir = rtf_path.with_suffix(".txt")
        if not txt_in_rtf_dir.exists():
            try:
                subprocess.run(
                    ["textutil", "-convert", "txt", str(rtf_path)],
                    check=True,
                    capture_output=True,
                )
                converted += 1
            except subprocess.CalledProcessError as e:
                print(f"  textutil failed on {rtf_path.name}: {e.stderr.decode()}")
                continue

        if not txt_in_rtf_dir.exists():
            print(f"  No text output for {rtf_path.name}")
            continue

        # Match to AUTHORITIES.md citation (pass RTF content for disambiguation)
        try:
            rtf_content = rtf_path.read_text(errors="replace")[:5000]
        except OSError:
            rtf_content = ""
        brief_citation = _match_rtf_to_citation(rtf_path, citations, rtf_content)

        if brief_citation:
            # Check if the brief's citation differs from the actual case
            corrected = _check_cite_discrepancy(brief_citation, rtf_path)

            if corrected and corrected != brief_citation:
                # Brief has an error — use correct citation for file,
                # create symlink with "-" prefix for the brief's citation
                new_name = sanitize_filename(corrected + ".txt")
                final_path = auth_dir / new_name

                if final_path.exists():
                    print(f"  {new_name} (already exists)")
                    skipped += 1
                    txt_in_rtf_dir.unlink(missing_ok=True)
                else:
                    txt_in_rtf_dir.rename(final_path)
                    print(f"  {rtf_path.name} -> {final_path.name}")
                    renamed += 1

                # Create symlink for the brief's erroneous citation
                link_name = sanitize_filename("-" + brief_citation + ".txt")
                link_path = auth_dir / link_name
                if not link_path.exists() and final_path.exists():
                    os.symlink(final_path.name, link_path)
                    print(f"    symlink: {link_name} -> {final_path.name}")
                    symlinks += 1
            else:
                # No discrepancy — use AUTHORITIES.md citation directly
                new_name = sanitize_filename(brief_citation + ".txt")
                final_path = auth_dir / new_name

                if final_path.exists():
                    print(f"  {new_name} (already exists)")
                    skipped += 1
                    txt_in_rtf_dir.unlink(missing_ok=True)
                else:
                    txt_in_rtf_dir.rename(final_path)
                    print(f"  {rtf_path.name} -> {final_path.name}")
                    renamed += 1
        else:
            # No AUTHORITIES.md match — use RTF filename
            stem = re.sub(r'^\d+\s*-\s*', '', rtf_path.stem)
            new_name = sanitize_filename(stem + ".txt")
            final_path = auth_dir / new_name
            unmatched.append(rtf_path.name)

            if final_path.exists():
                print(f"  {new_name} (already exists)")
                skipped += 1
                txt_in_rtf_dir.unlink(missing_ok=True)
            else:
                txt_in_rtf_dir.rename(final_path)
                print(f"  {rtf_path.name} -> {final_path.name}")
                renamed += 1

    print(f"\n  Converted {converted} RTFs, renamed {renamed} files, "
          f"skipped {skipped} (already exist).")
    if symlinks:
        print(f"  Created {symlinks} symlinks for erroneous citations in briefs.")
    if unmatched:
        print(f"  {len(unmatched)} RTFs could not be matched to AUTHORITIES.md:")
        for name in unmatched:
            print(f"    - {name}")
    print(f"  RTF originals remain in: {rtf_dir}")
