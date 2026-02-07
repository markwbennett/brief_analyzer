"""Step 2b: Download cases from CourtListener's free API.

Tries CourtListener before Westlaw to reduce manual interaction.
Saves opinion text as .txt files directly in authorities/.
Writes COURTLISTENER_RESULTS.json so the Westlaw step knows what to skip.
"""

import json
import re
import time
from pathlib import Path

import requests

from ..config import ProjectConfig
from ..utils.file_utils import sanitize_filename


# CourtListener API base
API_BASE = "https://www.courtlistener.com/api/rest/v4"

# Parse **CaseName, Citation** entries from AUTHORITIES.md (same as verify step)
CASE_ENTRY_RE = re.compile(r"^\*\*(.+?)\*\*$", re.MULTILINE)

# Extract volume/reporter/page from a citation string
CITE_RE = re.compile(
    r"(\d+)\s+"
    r"(S\.W\.(?:2d|3d)|F\.(?:2d|3d|4th)|F\.\s*App'x|F\.\s*Supp\.(?:\s*2d)?|"
    r"U\.S\.|S\.\s*Ct\.|L\.\s*Ed\.(?:\s*2d)?|A\.2d|N\.E\.2d|P\.2d|P\.3d|Tex\.)"
    r"\s+(\d+)"
)

WL_CITE_RE = re.compile(r"(\d{4})\s+WL\s+(\d+)")

# Minimum opinion text length to consider it usable
MIN_TEXT_LENGTH = 200

# Delay between API requests (seconds) to stay under rate limits
REQUEST_DELAY = 1.1


def run(config: ProjectConfig):
    """Download cases from CourtListener API."""
    if not config.courtlistener.api_token:
        raise ValueError(
            "CourtListener API token not set.\n"
            "Set the COURTLISTENER_TOKEN environment variable, or add\n"
            "  courtlistener:\n"
            "    api_token: your_token_here\n"
            "to brief_config.yaml."
        )

    auth_md_path = config.project_dir / "AUTHORITIES.md"
    if not auth_md_path.exists():
        raise FileNotFoundError("AUTHORITIES.md not found. Run the 'authorities' step first.")

    auth_dir = config.authorities_dir
    auth_dir.mkdir(exist_ok=True)

    md_text = auth_md_path.read_text(errors="replace")
    entries = _parse_authorities_entries(md_text)
    print(f"  Found {len(entries)} case entries in AUTHORITIES.md")

    # Filter out entries that already have matching files
    needed = []
    already_have = []
    for entry in entries:
        if _file_exists_for_citation(entry, auth_dir):
            already_have.append(entry)
        else:
            needed.append(entry)

    if already_have:
        print(f"  Skipping {len(already_have)} cases already in authorities/")
    if not needed:
        print("  All cases already downloaded. Nothing to do.")
        _write_results(config.project_dir, [], [])
        return

    print(f"  Looking up {len(needed)} cases on CourtListener...")

    session = requests.Session()
    session.headers["Authorization"] = f"Token {config.courtlistener.api_token}"

    # Build lookup text -- one citation per line for the API
    lookup_lines = []
    for entry in needed:
        # Use the standard citation from the ** entry
        # The API is good at parsing standard-format citations
        lookup_lines.append(entry["full_entry"])

    lookup_text = "\n".join(lookup_lines)

    # POST to citation-lookup
    matches = _citation_lookup(lookup_text, session)
    print(f"  Citation lookup returned {len(matches)} cluster matches")

    found = []
    not_found = []

    # Match API results back to our entries by volume+page or WL number
    matched_clusters = _match_results_to_entries(needed, matches)

    for entry in needed:
        cluster_id = matched_clusters.get(entry["key"])
        if not cluster_id:
            not_found.append(entry["full_entry"])
            continue

        # Fetch opinion text
        text = _fetch_opinion_text(cluster_id, session)
        if not text or len(text.strip()) < MIN_TEXT_LENGTH:
            print(f"    {entry['case_name']}: text too short or empty, skipping")
            not_found.append(entry["full_entry"])
            continue

        # Build filename from the AUTHORITIES.md entry
        filename = sanitize_filename(entry["full_entry"] + ".txt")
        filepath = auth_dir / filename

        filepath.write_text(text, encoding="utf-8")
        found.append(entry["full_entry"])
        print(f"    Saved: {filename}")

    _write_results(config.project_dir, found, not_found)

    print(f"\n  CourtListener results: {len(found)} found, {len(not_found)} not found")
    if not_found:
        print("  Cases not found on CourtListener (will need Westlaw):")
        for name in not_found:
            print(f"    - {name}")


def _parse_authorities_entries(text: str) -> list[dict]:
    """Parse case entries from the ## CASES section of AUTHORITIES.md.

    Returns list of dicts with: full_entry, case_name, volume, reporter, page,
    wl_year, wl_number, key (for dedup matching).
    """
    entries = []
    in_cases_section = False

    for line in text.split("\n"):
        stripped = line.strip()
        # Look for the cases section header (handles ## CASES and ## Cases)
        if re.match(r"^##\s+CASES\s*$", stripped, re.IGNORECASE):
            in_cases_section = True
            continue
        if stripped.startswith("## ") and in_cases_section:
            break  # hit next section

        if not in_cases_section:
            continue

        # Match ### headings: ### Case Name, Citation
        # or **bold** entries: **Case Name, Citation**
        heading_match = re.match(r"^###\s+(?:\d+\.\s+)?(.+)$", stripped)
        bold_match = CASE_ENTRY_RE.match(stripped)

        if heading_match:
            entry_text = heading_match.group(1).strip()
        elif bold_match:
            entry_text = bold_match.group(1).strip()
        else:
            continue

        # Skip non-case bold lines (e.g. "Group 1 (40 citations):")
        is_case = (
            " v. " in entry_text
            or " v " in entry_text
            or entry_text.lower().startswith("ex parte ")
            or entry_text.lower().startswith("in re ")
        )
        if not is_case:
            continue
        info = {
            "full_entry": entry_text,
            "case_name": "",
            "volume": "",
            "reporter": "",
            "page": "",
            "wl_year": "",
            "wl_number": "",
            "key": "",
        }

        # Extract case name
        name_match = re.match(r"(.+?),\s*(?:No\.|[0-9])", entry_text)
        if name_match:
            info["case_name"] = name_match.group(1).strip()
        else:
            name_match2 = re.match(r"(.+?),\s", entry_text)
            if name_match2:
                info["case_name"] = name_match2.group(1).strip()

        # Extract reporter citation
        cite_m = CITE_RE.search(entry_text)
        if cite_m:
            info["volume"] = cite_m.group(1)
            info["reporter"] = cite_m.group(2)
            info["page"] = cite_m.group(3)

        # Extract WL citation
        wl_m = WL_CITE_RE.search(entry_text)
        if wl_m:
            info["wl_year"] = wl_m.group(1)
            info["wl_number"] = wl_m.group(2)

        # Build a matching key: volume+page for reporter cites, wl_number for WL cites
        if info["volume"] and info["page"]:
            info["key"] = f"{info['volume']}_{info['page']}"
        elif info["wl_number"]:
            info["key"] = f"wl_{info['wl_number']}"
        else:
            info["key"] = entry_text[:60]

        entries.append(info)

    return entries


def _file_exists_for_citation(entry: dict, auth_dir: Path) -> bool:
    """Check if a matching .txt file already exists in authorities/.

    Matches on volume/reporter/page in filename, WL number in filename,
    or case name in filename.
    """
    existing = list(auth_dir.glob("*.txt"))
    volume = entry["volume"]
    reporter = entry["reporter"]
    page = entry["page"]
    wl_number = entry["wl_number"]

    for f in existing:
        fname = f.name

        # Check volume/reporter/page
        if volume and reporter and page:
            cite_str = f"{volume} {reporter} {page}"
            if cite_str in fname:
                return True

        # Check WL number
        if wl_number and wl_number in fname:
            return True

    return False


def _citation_lookup(text: str, session: requests.Session) -> list[dict]:
    """POST text to CourtListener's citation-lookup endpoint.

    Returns list of dicts with citation info and cluster URLs.
    """
    url = f"{API_BASE}/citation-lookup/"

    try:
        resp = session.post(
            url,
            data={"text": text},
            timeout=30,
        )
        # Handle rate limiting
        if resp.status_code == 429:
            data = resp.json()
            print(f"  Rate limited. Waiting 60s...")
            time.sleep(60)
            resp = session.post(url, data={"text": text}, timeout=30)
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.json()
    except requests.RequestException as e:
        print(f"  Citation lookup failed: {e}")
        return []


def _match_results_to_entries(entries: list[dict], matches: list[dict]) -> dict:
    """Match citation-lookup results back to our entry list.

    The API returns a list of dicts, each with 'citation', 'status', and
    'clusters' (list of cluster objects with 'id', 'sub_opinions', etc.).
    We match by volume+page from the citation field.

    Returns dict mapping entry key -> cluster_id.
    """
    result = {}

    for match in matches:
        clusters = match.get("clusters", [])
        citation = match.get("citation", "")

        if not clusters or match.get("status") != 200:
            continue

        # Cluster is a dict with 'id' field
        cluster = clusters[0]
        if isinstance(cluster, dict):
            cluster_id = str(cluster.get("id", ""))
        else:
            # Fallback: might be a URL string
            cluster_id = _extract_id_from_url(str(cluster))
        if not cluster_id:
            continue

        # Extract volume and page from the matched citation
        cite_m = CITE_RE.search(citation)
        if cite_m:
            vol = cite_m.group(1)
            pg = cite_m.group(3)
            key = f"{vol}_{pg}"
            result[key] = cluster_id
            continue

        # Try WL match
        wl_m = WL_CITE_RE.search(citation)
        if wl_m:
            key = f"wl_{wl_m.group(2)}"
            result[key] = cluster_id

    return result


def _extract_id_from_url(url: str) -> str:
    """Extract numeric ID from a CourtListener API URL.

    e.g. 'https://www.courtlistener.com/api/rest/v4/clusters/12345/'  -> '12345'
    or   '/api/rest/v4/clusters/12345/'  -> '12345'
    """
    m = re.search(r"/(\d+)/?$", url)
    return m.group(1) if m else ""


def _fetch_opinion_text(cluster_id: str, session: requests.Session) -> str:
    """Fetch opinion text for a cluster.

    Gets the cluster to find sub_opinions, then fetches each opinion's text.
    Prefers plain_text; falls back to html_with_citations stripped of tags.
    """
    # Get cluster
    cluster_url = f"{API_BASE}/clusters/{cluster_id}/"
    try:
        resp = session.get(cluster_url, timeout=30)
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        cluster_data = resp.json()
    except requests.RequestException as e:
        print(f"    Failed to fetch cluster {cluster_id}: {e}")
        return ""

    sub_opinions = cluster_data.get("sub_opinions", [])
    if not sub_opinions:
        return ""

    # Fetch each sub-opinion and concatenate text
    texts = []
    for op_url in sub_opinions:
        op_id = _extract_id_from_url(op_url)
        if not op_id:
            continue

        opinion_url = f"{API_BASE}/opinions/{op_id}/"
        try:
            resp = session.get(opinion_url, timeout=30)
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            op_data = resp.json()
        except requests.RequestException as e:
            print(f"    Failed to fetch opinion {op_id}: {e}")
            continue

        # Prefer plain_text, fall back to html_with_citations
        text = op_data.get("plain_text", "").strip()
        if not text:
            html = op_data.get("html_with_citations", "")
            if html:
                text = _strip_html(html)

        if text:
            texts.append(text)

    return "\n\n".join(texts)


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    # Remove tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _write_results(project_dir: Path, found: list[str], not_found: list[str]):
    """Write COURTLISTENER_RESULTS.json."""
    results = {
        "found": found,
        "not_found": not_found,
    }
    path = project_dir / "COURTLISTENER_RESULTS.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Wrote {path.name}")
