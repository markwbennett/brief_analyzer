#!/usr/bin/env python3
"""Line-by-line cite-checker for DOCX appellate briefs.

Extracts text from a .docx file paragraph by paragraph. For each paragraph
that contains a citation (case, record, or State's Brief), sends the
paragraph text along with the full text of each cited authority to Claude
for verification.

Checks:
  - Quotations are exact (modulo ellipses and [brackets])
  - Assertions about cases are accurate
  - Record references (RR/CR volume:page) match the actual record
  - References to the State's Brief are accurate

Usage:
    python docx_citecheck.py <brief.docx> [--output CITECHECK_LINEBY.md]

The script expects an `authorities/` directory and optionally a `record/`
directory (with record_index.json) and State's Brief .txt in the same
folder as the .docx.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docx


# ---------------------------------------------------------------------------
# Citation detection patterns
# ---------------------------------------------------------------------------

# Reporter abbreviations (shared across patterns) — capturing group
_REPORTERS = (
    r'(S\.W\.(?:2d|3d)|U\.S\.|F\.(?:2d|3d|4th)|F\.\s*Supp\.(?:\s*2d)?|'
    r'Fed\.?\s*App(?:x|\'x)\.?|N\.E\.(?:2d)?|A\.(?:2d)?|P\.(?:2d|3d)?|'
    r'N\.M\.|Wash\.App\.|Ill\.App\.3d|Pa\.Super\.|Tex\.|Md\.|F\.4th)'
)

# Full case citations: Name v. Name, VOL Reporter PAGE
CASE_CITE_RE = re.compile(
    r'([A-Z][A-Za-z\'\u2019\-]+(?:\s+(?:ex\s+rel\.\s+)?[A-Za-z\'\u2019\-]+)*'
    r'\s+v\.\s+'
    r'[A-Z][A-Za-z\'\u2019\-]+(?:\s+[A-Za-z\'\u2019\-]+)*)'
    r',?\s*'
    r'(\d+)\s+'
    + _REPORTERS +
    r'\s+(\d+)'
)

# Short-form citations: Name, VOL Reporter at PAGE or just VOL Reporter at PAGE
SHORT_CITE_RE = re.compile(
    r'([A-Z][A-Za-z\'\u2019\-]+(?:\s+[A-Za-z\'\u2019\-]+){0,3})'
    r',\s*'
    r'(\d+)\s+'
    + _REPORTERS +
    r'\s+(?:at\s+)?(\d+)'
)

# Bare reporter cite (for detection only): VOL Reporter PAGE
BARE_REPORTER_RE = re.compile(
    r'(\d+)\s+' + _REPORTERS + r'\s+(\d+)'
)

# Westlaw cite: YEAR WL NUMBER
WL_CITE_RE = re.compile(r'\d{4}\s+WL\s+\d+')

# Reporter's Record: RR{vol}:{page} or (RR{vol}:{page})
RR_CITE_RE = re.compile(r'RR(\d+):(\d+)')

# Clerk's Record: CR:{page} or CR at {page}
CR_CITE_RE = re.compile(r'CR(?:\s*(?:at\s+))?:?\s*(\d+)')

# State's Brief explicit page reference (handle curly apostrophe U+2019 and straight)
STATE_BRIEF_RE = re.compile(r"State[\u2019']s\s+Br(?:ief|\.)\s+(?:at\s+)?(\d+(?:\s*[-\u2013]\s*\d+)?)", re.IGNORECASE)

# Broader State's Brief reference — "The State argues/cites/concedes/claims..." or "State's argument/position"
STATE_ARGUES_RE = re.compile(
    r"(?:"
    r"(?:The\s+)?State\s+(?:argu|cit|conced|claim|acknowledg|assert|content|maintain|reli)"  # "The State argues"
    r"|State[\u2019']s\s+(?:\w+\s+){0,3}(?:argu|cit|position|response|brief|claim|content)"  # "State's [adj] argument"
    r"|State[\u2019']s\s+Br"  # "State's Br."
    r")",
    re.IGNORECASE
)

# Exhibit reference: SX{num} {timestamp}
EXHIBIT_RE = re.compile(r'SX(\d+)\s+([\d:]+(?:\s*[-\u2013]\s*[\d:]+)?)')

# Id. or Id. at PAGE
ID_CITE_RE = re.compile(r'\b[Ii]d\.\s*(?:at\s+(\d+))?')


def _clean_for_cite_match(text: str) -> str:
    """Strip formatting artifacts that interfere with citation matching."""
    # DOCX italic markers show up as * in python-docx text
    return text.replace("*", "")


def has_citation(text: str) -> bool:
    """Return True if the paragraph contains any checkable citation."""
    t = _clean_for_cite_match(text)
    return bool(
        CASE_CITE_RE.search(t)
        or SHORT_CITE_RE.search(t)
        or BARE_REPORTER_RE.search(t)
        or WL_CITE_RE.search(t)
        or RR_CITE_RE.search(t)
        or CR_CITE_RE.search(t)
        or STATE_BRIEF_RE.search(t)
        or STATE_ARGUES_RE.search(t)
        or EXHIBIT_RE.search(t)
        or ID_CITE_RE.search(t)
    )


# ---------------------------------------------------------------------------
# Authority file matching
# ---------------------------------------------------------------------------

def load_authorities(auth_dir: Path) -> dict[str, str]:
    """Load all .txt authority files into {filename: text}."""
    files = {}
    for f in sorted(auth_dir.glob("*.txt")):
        if f.name.startswith("-"):
            continue  # skip symlink aliases
        try:
            files[f.name] = f.read_text(errors="replace")
        except Exception as e:
            print(f"  Warning: could not read {f.name}: {e}", file=sys.stderr)
    return files


def find_authority(case_name: str, volume: str, reporter: str, page: str,
                   auth_files: dict[str, str]) -> tuple[str, str] | None:
    """Find authority file by citation components."""
    cite_pattern = f"{volume} {reporter} {page}" if reporter != "WL" else f"WL {page}"

    # Match in filename
    for fname, text in auth_files.items():
        if cite_pattern.replace(" ", "") in fname.replace(" ", ""):
            return (fname, text)
        if cite_pattern in fname:
            return (fname, text)

    # Looser filename match
    for fname, text in auth_files.items():
        if volume and page and volume in fname and page in fname:
            # Check reporter abbreviation loosely
            rep_short = reporter.replace(".", "").replace(" ", "").lower()
            fname_clean = fname.replace(".", "").replace(" ", "").lower()
            if rep_short in fname_clean:
                return (fname, text)

    # Match by case name + either volume or page
    if case_name:
        first_party = case_name.split(" v.")[0].split(" v ")[0].strip()
        last_word = first_party.split()[-1].lower() if first_party else ""
        if last_word and last_word not in ("state", "the", "united", "states", "people", "com."):
            for fname, text in auth_files.items():
                if last_word in fname.lower() and (volume in fname or page in fname):
                    return (fname, text)

    # Match in file content header
    for fname, text in auth_files.items():
        header = text[:3000]
        if volume and reporter and page:
            if f"{volume} {reporter} {page}" in header:
                return (fname, text)

    # Last resort: match by case name alone (for parallel citations)
    if case_name:
        first_party = case_name.split(" v.")[0].split(" v ")[0].strip()
        last_word = first_party.split()[-1].lower() if first_party else ""
        if last_word and len(last_word) > 3 and last_word not in ("state", "the", "united", "states", "people", "com."):
            for fname, text in auth_files.items():
                if last_word in fname.lower():
                    return (fname, text)

    return None


def extract_case_cites(text: str) -> list[dict]:
    """Extract all case citations from a paragraph."""
    text = _clean_for_cite_match(text)
    cites = []
    seen = set()

    # Full citations: Name v. Name, VOL Reporter PAGE
    for m in CASE_CITE_RE.finditer(text):
        name = m.group(1).strip()
        vol = m.group(2)
        rep = m.group(3)
        pg = m.group(4)
        key = f"{vol}_{rep}_{pg}"
        if key not in seen:
            seen.add(key)
            cites.append({
                "case_name": name,
                "volume": vol,
                "reporter": rep,
                "page": pg,
                "type": "case",
            })

    # Short-form citations: Name, VOL Reporter at PAGE
    for m in SHORT_CITE_RE.finditer(text):
        name = m.group(1).strip()
        vol = m.group(2)
        rep = m.group(3)
        pg = m.group(4)
        key = f"{vol}_{rep}_{pg}"
        if key not in seen:
            seen.add(key)
            cites.append({
                "case_name": name,
                "volume": vol,
                "reporter": rep,
                "page": pg,
                "type": "case",
            })

    # Westlaw citations
    for m in WL_CITE_RE.finditer(text):
        wl = m.group(0)
        if wl not in seen:
            seen.add(wl)
            cites.append({
                "case_name": "",
                "volume": "",
                "reporter": "WL",
                "page": wl.split("WL")[1].strip(),
                "type": "case",
            })

    return cites


def extract_record_refs(text: str) -> list[dict]:
    """Extract record references from a paragraph."""
    text = _clean_for_cite_match(text)
    refs = []
    for m in RR_CITE_RE.finditer(text):
        refs.append({"type": "rr", "volume": int(m.group(1)), "page": int(m.group(2))})
    for m in CR_CITE_RE.finditer(text):
        refs.append({"type": "cr", "page": int(m.group(1))})
    for m in EXHIBIT_RE.finditer(text):
        refs.append({"type": "exhibit", "number": m.group(1), "timestamp": m.group(2)})
    return refs


def extract_state_brief_refs(text: str) -> list[dict]:
    """Extract State's Brief page references."""
    text = _clean_for_cite_match(text)
    refs = []
    for m in STATE_BRIEF_RE.finditer(text):
        refs.append({"type": "state_brief", "pages": m.group(1)})
    return refs


# ---------------------------------------------------------------------------
# Record lookup
# ---------------------------------------------------------------------------

def load_record_index(record_dir: Path) -> dict | None:
    """Load record_index.json if it exists."""
    idx_path = record_dir / "record_index.json"
    if not idx_path.exists():
        return None
    try:
        return json.loads(idx_path.read_text())
    except Exception:
        return None


def get_record_page(record_index: dict, vol_type: str, vol_num: int, page: int) -> str | None:
    """Get the text of a specific record page."""
    if not record_index:
        return None
    pages = record_index.get("pages", [])
    vol_ref = f"{vol_type}{vol_num}" if vol_num > 0 else vol_type
    for p in pages:
        if p.get("volume") == vol_ref and p.get("page") == page:
            return p.get("text", "")
    return None


# ---------------------------------------------------------------------------
# Claude verification
# ---------------------------------------------------------------------------

VERIFY_PROMPT = """You are a meticulous legal cite-checker. You are checking a single paragraph from an appellate reply brief against ONE source.

## Your task

Check every assertion in this paragraph that relates to the source provided. Specifically:

1. **Quotations**: Any text in quotation marks attributed to this source must be EXACT—verbatim. Ellipses (\u2026 or "...") may replace omitted text, and brackets ("[ ]") may indicate alterations—both are acceptable if the surrounding text is otherwise exact. Flag any quotation that adds, removes, or changes words beyond these conventions.

2. **Case assertions**: When the brief says a case "held" something, or describes what a court "found" or "concluded," verify that the case actually says that. Check the holding, the reasoning, and any pin cites.

3. **Record assertions**: When the brief cites the Reporter's Record (RR) or Clerk's Record (CR) for a factual assertion, verify the cited page supports the assertion.

4. **State's Brief assertions**: When the brief describes what "the State argues" or quotes the State's Brief, verify accuracy against the State's Brief text.

5. **Pin cites**: Verify that pin-cite page numbers correspond to the actual location of the quoted or cited material in the source.

Only check assertions that relate to THIS source. Skip assertions about other sources.

## Output format

For each assertion you check, output one entry. Output a JSON array:

```json
[
  {{
    "assertion": "<the specific claim being checked>",
    "source": "<which source: case name, RR vol:page, State's Br., etc.>",
    "status": "VERIFIED|INACCURATE|QUOTE_ERROR|PIN_CITE_ERROR|UNSUPPORTED",
    "detail": "<explanation—if verified, say so briefly; if error, explain precisely what's wrong>"
  }}
]
```

Status meanings:
- VERIFIED: The assertion is accurate and any quotation is exact.
- INACCURATE: The assertion misrepresents what the source says.
- QUOTE_ERROR: A quotation is not verbatim (beyond ellipses/brackets).
- PIN_CITE_ERROR: The pin cite page doesn't contain the referenced material.
- UNSUPPORTED: The source doesn't address the proposition at all.

Output ONLY the JSON array. No commentary, no markdown fencing. Begin with [ and end with ].

## Paragraph from the brief (paragraph {para_num}):

{paragraph}

## Source:

{source}
"""


def claude_env():
    """Environment with ANTHROPIC_API_KEY removed."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _call_claude(prompt: str, model: str, label: str, max_retries: int = 3) -> list[dict]:
    """Send a prompt to Claude and parse the JSON array response."""
    for attempt in range(max_retries):
        try:
            cmd = ["claude", "--print", "--model", model]
            result = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                timeout=300, env=claude_env(),
            )

            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                print(f"    {label}: Claude error (attempt {attempt+1}): {err[:200]}", file=sys.stderr)
                if attempt < max_retries - 1:
                    time.sleep(15 * (attempt + 1))
                continue

            text = result.stdout.strip()
            if not text:
                print(f"    {label}: empty response (attempt {attempt+1})", file=sys.stderr)
                if attempt < max_retries - 1:
                    time.sleep(15 * (attempt + 1))
                continue

            return parse_json_array(text, label)

        except subprocess.TimeoutExpired:
            print(f"    {label}: timeout (attempt {attempt+1})", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(15 * (attempt + 1))

    return []


def verify_paragraph(para_num: int, paragraph: str, sources: list[tuple[str, str]],
                     model: str = "opus", workers: int = 4) -> list[dict]:
    """Verify a paragraph against each source in parallel (one prompt per source).

    sources: list of (label, source_text) — e.g. ("Bell v. Wolfish, 441 U.S. 520", full_text)
    Returns merged list of assertion dicts from all sources.
    """
    if not sources:
        return []

    all_assertions = []

    # Build prompts
    tasks = []
    for label, source_text in sources:
        prompt = VERIFY_PROMPT.format(
            para_num=para_num,
            paragraph=paragraph,
            source=f"=== {label} ===\n{source_text}",
        )
        tasks.append((prompt, label))

    # Run in parallel
    with ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
        futures = {}
        for prompt, label in tasks:
            future = executor.submit(_call_claude, prompt, model, f"Para {para_num}/{label}")
            futures[future] = label

        for future in as_completed(futures):
            label = futures[future]
            try:
                results = future.result()
                all_assertions.extend(results)
            except Exception as e:
                print(f"    Para {para_num}/{label}: FAILED — {e}", file=sys.stderr)

    return all_assertions


def parse_json_array(text: str, label: str = "") -> list[dict]:
    """Extract a JSON array from text that may contain markdown fences."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

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

    print(f"    {label}: could not parse JSON ({len(text)} chars): {text[:200]}", file=sys.stderr)
    return []


# ---------------------------------------------------------------------------
# Source gathering
# ---------------------------------------------------------------------------


def gather_sources(paragraph: str, auth_files: dict[str, str],
                   record_index: dict | None, state_brief_text: str | None,
                   last_case: dict | None) -> tuple[list[tuple[str, str]], dict | None]:
    """Gather all source materials referenced in this paragraph.

    Returns (sources, last_case_cited) where sources is a list of
    (label, full_text) tuples — one per source, each sent as a
    separate verification prompt.
    """
    sources = []
    current_last_case = last_case
    clean_para = _clean_for_cite_match(paragraph)

    # --- State's Brief ---
    sb_refs = extract_state_brief_refs(paragraph)
    needs_state_brief = bool(sb_refs) or bool(STATE_ARGUES_RE.search(clean_para))
    if needs_state_brief and state_brief_text:
        sources.append(("State's Brief", state_brief_text))

    # --- Record references (group all record pages into one source) ---
    record_refs = extract_record_refs(paragraph)
    record_parts = []
    for ref in record_refs:
        if ref["type"] == "rr":
            page_text = get_record_page(record_index, "RR", ref["volume"], ref["page"])
            if page_text:
                record_parts.append(f"--- RR{ref['volume']}:{ref['page']} ---\n{page_text}")
            else:
                record_parts.append(f"--- RR{ref['volume']}:{ref['page']} --- [PAGE NOT FOUND IN INDEX]")
        elif ref["type"] == "cr":
            page_text = get_record_page(record_index, "CR", 0, ref["page"])
            if page_text:
                record_parts.append(f"--- CR:{ref['page']} ---\n{page_text}")
            else:
                record_parts.append(f"--- CR:{ref['page']} --- [PAGE NOT FOUND IN INDEX]")
        elif ref["type"] == "exhibit":
            record_parts.append(f"--- SX{ref['number']} {ref['timestamp']} --- [EXHIBIT VERIFICATION NOT AVAILABLE]")
    if record_parts:
        sources.append(("Record", "\n\n".join(record_parts)))

    # --- Case citations (one source per case) ---
    case_cites = extract_case_cites(paragraph)
    for cite in case_cites:
        match = find_authority(
            cite["case_name"], cite["volume"], cite["reporter"], cite["page"],
            auth_files,
        )
        if match:
            fname, text = match
            sources.append((fname, text))
            current_last_case = {"name": fname, "text": text}

    # Handle Id. citations — refer to the last-cited case
    if ID_CITE_RE.search(clean_para) and not case_cites:
        if last_case:
            sources.append((f"{last_case['name']} (Id.)", last_case["text"]))

    # Update last_case if we had new case cites
    if case_cites and current_last_case:
        last_case = current_last_case

    return sources, current_last_case


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def extract_paragraphs(docx_path: Path) -> list[tuple[int, str]]:
    """Extract non-empty paragraphs from a DOCX, returning (index, text)."""
    doc = docx.Document(str(docx_path))
    paragraphs = []
    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if text:
            paragraphs.append((i, text))
    return paragraphs


def is_body_paragraph(text: str) -> bool:
    """Determine if a paragraph is part of the brief's body (not TOC, index, etc.)."""
    # Skip very short lines that are likely headers/section markers
    if len(text) < 20:
        return False
    # Skip TOC entries (contain tab-separated page numbers)
    if "\t" in text and re.search(r'\d+$', text.strip()):
        return False
    # Skip index entries (citations with page numbers)
    if re.match(r'^[A-Z].*\d+(?:,\s*\d+)*$', text.strip()):
        return False
    # Skip certificate/prayer boilerplate markers
    lower = text.lower()
    if lower.startswith("certificate of") or lower == "prayer":
        return False
    return True


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(results: list[dict]) -> str:
    """Format all results into a markdown report."""
    lines = ["# Line-by-Line Cite-Check Report\n"]

    # Count totals
    total_assertions = 0
    verified = 0
    errors = 0
    not_checked = 0

    for r in results:
        for a in r.get("assertions", []):
            total_assertions += 1
            status = a.get("status", "")
            if status == "VERIFIED":
                verified += 1
            elif status == "NOT_CHECKED":
                not_checked += 1
            elif status in ("INACCURATE", "QUOTE_ERROR", "PIN_CITE_ERROR", "UNSUPPORTED"):
                errors += 1

    lines.append(f"**Summary**: {len(results)} paragraphs checked, "
                 f"{total_assertions} assertions found. "
                 f"{verified} verified, {errors} errors, {not_checked} not checked.\n")

    # Errors section first
    error_entries = []
    for r in results:
        for a in r.get("assertions", []):
            if a.get("status") in ("INACCURATE", "QUOTE_ERROR", "PIN_CITE_ERROR", "UNSUPPORTED"):
                error_entries.append((r["para_num"], r["text"][:100], a))

    if error_entries:
        lines.append("## Errors and Issues\n")
        for para_num, para_preview, a in error_entries:
            lines.append(f"### Paragraph {para_num}")
            lines.append(f"> {para_preview}...")
            lines.append(f"- **Status**: {a['status']}")
            lines.append(f"- **Assertion**: {a['assertion']}")
            lines.append(f"- **Source**: {a['source']}")
            lines.append(f"- **Detail**: {a['detail']}")
            lines.append("")

    # Full paragraph-by-paragraph results
    lines.append("## Paragraph-by-Paragraph Results\n")
    for r in results:
        para_num = r["para_num"]
        text = r["text"]
        assertions = r.get("assertions", [])

        # Determine overall status for this paragraph
        statuses = [a.get("status", "") for a in assertions]
        has_error = any(s in ("INACCURATE", "QUOTE_ERROR", "PIN_CITE_ERROR", "UNSUPPORTED") for s in statuses)
        all_verified = all(s == "VERIFIED" for s in statuses) if statuses else False

        if has_error:
            marker = "ISSUE"
        elif all_verified:
            marker = "OK"
        else:
            marker = "PARTIAL"

        lines.append(f"### [{marker}] Paragraph {para_num}")
        # Show first 200 chars of paragraph
        preview = text[:200] + ("..." if len(text) > 200 else "")
        lines.append(f"> {preview}\n")

        if not assertions:
            lines.append("*No verifiable assertions returned.*\n")
            continue

        for a in assertions:
            status = a.get("status", "?")
            icon = {
                "VERIFIED": "PASS",
                "INACCURATE": "FAIL",
                "QUOTE_ERROR": "FAIL",
                "PIN_CITE_ERROR": "FAIL",
                "UNSUPPORTED": "FAIL",
                "NOT_CHECKED": "SKIP",
            }.get(status, "?")

            lines.append(f"- **[{icon}]** {a.get('assertion', '')}")
            lines.append(f"  - Source: {a.get('source', '?')}")
            lines.append(f"  - Status: {status}")
            if a.get("detail"):
                lines.append(f"  - Detail: {a['detail']}")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Line-by-line DOCX brief cite-checker")
    parser.add_argument("docx", type=Path, help="Path to the .docx brief")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output markdown file (default: CITECHECK_LINEBY.md in same dir)")
    parser.add_argument("--model", default="opus",
                        help="Claude model to use (default: opus)")
    parser.add_argument("--start", type=int, default=0,
                        help="Start from this paragraph index (for resuming)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only this many paragraphs (0 = all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show which paragraphs would be checked, without calling Claude")
    args = parser.parse_args()

    docx_path = args.docx.resolve()
    if not docx_path.exists():
        print(f"File not found: {docx_path}", file=sys.stderr)
        sys.exit(1)

    project_dir = docx_path.parent
    output_path = args.output or (project_dir / "CITECHECK_LINEBY.md")

    print(f"Brief: {docx_path.name}")
    print(f"Project dir: {project_dir}")

    # Load authorities
    auth_dir = project_dir / "authorities"
    if auth_dir.exists():
        auth_files = load_authorities(auth_dir)
        print(f"Loaded {len(auth_files)} authority files")
    else:
        auth_files = {}
        print("No authorities/ directory found")

    # Load record index
    record_dir = project_dir / "record"
    record_index = load_record_index(record_dir) if record_dir.exists() else None
    if record_index:
        n_pages = len(record_index.get("pages", []))
        print(f"Loaded record index ({n_pages} pages)")
    else:
        print("No record index found")

    # Load State's Brief
    state_brief_text = None
    for f in sorted(project_dir.glob("*.txt")):
        if "state" in f.name.lower() and "brief" in f.name.lower() and "notice" not in f.name.lower():
            state_brief_text = f.read_text(errors="replace")
            print(f"Loaded State's Brief: {f.name} ({len(state_brief_text):,} chars)")
            break
    if not state_brief_text:
        # Also check for the State's brief PDF text
        for f in sorted(project_dir.glob("*.txt")):
            if "state" in f.name.lower() and "notice" not in f.name.lower():
                state_brief_text = f.read_text(errors="replace")
                print(f"Loaded State's filing: {f.name} ({len(state_brief_text):,} chars)")
                break

    if not state_brief_text:
        print("No State's Brief text found")

    # Extract paragraphs
    paragraphs = extract_paragraphs(docx_path)
    print(f"Extracted {len(paragraphs)} non-empty paragraphs")

    # Filter to body paragraphs with citations
    # Skip front matter (TOC, index of authorities) — look for "Argument" or "Summary"
    body_start = 0
    for idx, (para_idx, text) in enumerate(paragraphs):
        lower = text.strip().lower()
        if lower in ("argument", "summary of reply argument", "summary of argument",
                      "summary of the argument"):
            body_start = idx
            break

    # Find where body ends (Prayer, Certificate, etc.)
    body_end = len(paragraphs)
    for idx in range(len(paragraphs) - 1, body_start, -1):
        lower = paragraphs[idx][1].strip().lower()
        if lower.startswith("certificate of") or lower == "prayer":
            body_end = idx
            # keep going backwards to find the earliest ending marker
        if lower in ("prayer",):
            body_end = idx
            break

    body_paragraphs = paragraphs[body_start:body_end]
    print(f"Body paragraphs: {len(body_paragraphs)} (indices {body_start}–{body_end})")

    # Filter to paragraphs that contain citations
    cite_paragraphs = [(i, para_idx, text) for i, (para_idx, text) in enumerate(body_paragraphs)
                       if has_citation(text)]
    print(f"Paragraphs with citations: {len(cite_paragraphs)}")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for i, para_idx, text in cite_paragraphs:
            case_cites = extract_case_cites(text)
            rr_refs = extract_record_refs(text)
            sb_refs = extract_state_brief_refs(text)
            cite_summary = []
            for c in case_cites:
                cite_summary.append(f"{c['case_name']}, {c['volume']} {c['reporter']} {c['page']}")
            for r in rr_refs:
                if r["type"] == "rr":
                    cite_summary.append(f"RR{r['volume']}:{r['page']}")
                elif r["type"] == "cr":
                    cite_summary.append(f"CR:{r['page']}")
            for s in sb_refs:
                cite_summary.append(f"State's Br. at {s['pages']}")
            print(f"\n[{para_idx}] {text[:120]}...")
            print(f"   Citations: {'; '.join(cite_summary)}")
        return

    # Process paragraphs
    results = []
    last_case = None
    start_time = time.time()

    # Load any existing partial results for resuming
    partial_path = output_path.with_suffix(".partial.json")
    if args.start > 0 and partial_path.exists():
        try:
            results = json.loads(partial_path.read_text())
            print(f"Resumed from {len(results)} previously checked paragraphs")
        except Exception:
            pass

    processed_count = 0
    for seq, (i, para_idx, text) in enumerate(cite_paragraphs):
        if seq < args.start:
            continue
        if args.limit and processed_count >= args.limit:
            print(f"\nReached --limit {args.limit}, stopping.")
            break

        elapsed = time.time() - start_time
        print(f"\n[{seq+1}/{len(cite_paragraphs)}] Para {para_idx} ({elapsed:.0f}s elapsed)")
        print(f"  {text[:100]}...")

        # Gather sources (list of (label, text) tuples — one per source)
        sources, last_case = gather_sources(text, auth_files, record_index,
                                            state_brief_text, last_case)

        total_kb = sum(len(t) for _, t in sources) / 1024
        source_labels = [label[:40] for label, _ in sources]
        print(f"  Sources ({len(sources)}): {', '.join(source_labels)} [{total_kb:.0f} KB total]")

        # Call Claude — one prompt per source, in parallel
        assertions = verify_paragraph(para_idx, text, sources, model=args.model)
        n_verified = sum(1 for a in assertions if a.get("status") == "VERIFIED")
        n_errors = sum(1 for a in assertions if a.get("status") in
                       ("INACCURATE", "QUOTE_ERROR", "PIN_CITE_ERROR", "UNSUPPORTED"))

        status_str = f"{n_verified} verified"
        if n_errors:
            status_str += f", {n_errors} ERRORS"
        print(f"  Result: {len(assertions)} assertions ({status_str})")

        results.append({
            "para_num": para_idx,
            "text": text,
            "assertions": assertions,
        })

        # Save partial results after each paragraph
        partial_path.write_text(json.dumps(results, indent=2))
        processed_count += 1

    # Generate report
    total_time = time.time() - start_time
    report = format_report(results)
    report += f"\n---\n*Generated in {total_time:.0f}s using model: {args.model}*\n"

    output_path.write_text(report)
    print(f"\nReport written to: {output_path}")
    print(f"Total time: {total_time:.0f}s")

    # Clean up partial file
    if partial_path.exists():
        partial_path.unlink()

    # Print error summary
    error_count = 0
    for r in results:
        for a in r.get("assertions", []):
            if a.get("status") in ("INACCURATE", "QUOTE_ERROR", "PIN_CITE_ERROR", "UNSUPPORTED"):
                error_count += 1

    if error_count:
        print(f"\n{error_count} issue(s) found. Review the report for details.")
    else:
        print("\nNo issues found.")


if __name__ == "__main__":
    main()
