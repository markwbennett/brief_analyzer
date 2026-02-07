"""Step 0: Fetch case filings from search.txcourts.gov."""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..config import ProjectConfig
from ..utils.file_utils import sanitize_filename

BASE_URL = "https://search.txcourts.gov"
CASE_URL = BASE_URL + "/Case.aspx?cn={case_number}&coa={coa}"
MEDIA_URL = BASE_URL + "/SearchMedia.aspx?MediaVersionID={media_id}"

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def run(config: ProjectConfig):
    """Download all filings for the given case number."""
    if not config.case_number:
        print("No case number provided; skipping fetch step.")
        return

    coa = config.infer_coa()
    case_url = CASE_URL.format(case_number=config.case_number, coa=coa)
    manifest_path = config.project_dir / "filings_manifest.json"
    case_info_path = config.project_dir / "case_info.json"

    # Load existing manifest to skip already-downloaded files
    existing_media_ids = set()
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        for entry in manifest.get("filings", []):
            if mid := entry.get("media_version_id"):
                existing_media_ids.add(mid)
    else:
        manifest = {"case_number": config.case_number, "coa": coa, "filings": []}

    print(f"Fetching case page: {case_url}")
    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(case_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract case metadata
    case_info = _extract_case_info(soup, config.case_number, coa)
    with open(case_info_path, "w") as f:
        json.dump(case_info, f, indent=2)
    print(f"Case: {case_info.get('style', 'Unknown')}")

    # Find all document links in both tables (Appellate Briefs + Case Events)
    filings = _extract_filings(soup)
    print(f"Found {len(filings)} filings with PDF attachments.")

    new_count = 0
    for filing in filings:
        media_id = filing["media_version_id"]
        if media_id in existing_media_ids:
            print(f"  Skipping (already downloaded): {filing['filename']}")
            continue

        # Download the PDF
        pdf_url = MEDIA_URL.format(media_id=media_id)
        pdf_path = config.project_dir / filing["filename"]

        print(f"  Downloading: {filing['filename']}")
        try:
            pdf_resp = session.get(pdf_url, timeout=60)
            pdf_resp.raise_for_status()
            pdf_path.write_bytes(pdf_resp.content)
            filing["downloaded"] = True
            new_count += 1
        except requests.RequestException as e:
            print(f"    FAILED: {e}")
            filing["downloaded"] = False

        manifest["filings"].append(filing)
        existing_media_ids.add(media_id)

        # Be polite to the server
        time.sleep(0.5)

    # Save updated manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDownloaded {new_count} new filings ({len(existing_media_ids)} total).")


def _extract_case_info(soup: BeautifulSoup, case_number: str, coa: str) -> dict:
    """Extract case metadata from the page."""
    info = {"case_number": case_number, "coa": coa}

    # Try to find case style
    style_el = soup.find("span", id=re.compile(r"lblStyle|lblCaseStyle", re.I))
    if style_el:
        info["style"] = style_el.get_text(strip=True)

    # Try to find trial court info
    tc_el = soup.find("span", id=re.compile(r"lblTrialCourt", re.I))
    if tc_el:
        info["trial_court"] = tc_el.get_text(strip=True)

    # Try to find panel
    panel_el = soup.find("span", id=re.compile(r"lblPanel", re.I))
    if panel_el:
        info["panel"] = panel_el.get_text(strip=True)

    return info


def _extract_filings(soup: BeautifulSoup) -> list[dict]:
    """Extract all filings with PDF download links from the page.

    txcourts.gov tables have main event rows (4 cells: Date, Event Type,
    Description/Party, Document) and nested sub-rows for each document.
    We find the main event rows, then extract documents from within them.
    """
    filings = []
    seen_media_ids = set()

    # Find the Briefs table and Events table by their header patterns
    for table in soup.find_all("table"):
        headers = table.find_all("th")
        hdr_texts = [h.get_text(strip=True) for h in headers]
        if "Date" not in hdr_texts or "Event Type" not in hdr_texts:
            continue

        # Determine which column is which
        date_col = hdr_texts.index("Date")
        event_col = hdr_texts.index("Event Type")
        # "Description" (Briefs table) or "Disposition" (Events table)
        desc_col = None
        for candidate in ("Description", "Disposition"):
            if candidate in hdr_texts:
                desc_col = hdr_texts.index(candidate)
                break

        # Walk through rows, tracking the current event context
        current_date = ""
        current_event = ""
        current_desc = ""

        for row in table.find_all("tr"):
            if row.find("th"):
                continue

            cells = row.find_all("td", recursive=False)

            # Main event rows have 4 cells; sub-rows (document detail) have 2
            if len(cells) >= 4:
                # This is a main event row -- extract context
                raw_date = cells[date_col].get_text(strip=True)
                date_match = re.match(r"(\d{1,2}/\d{1,2}/\d{4})", raw_date)
                if date_match:
                    parts = date_match.group(1).split("/")
                    current_date = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
                current_event = cells[event_col].get_text(strip=True)
                if desc_col is not None:
                    current_desc = cells[desc_col].get_text(strip=True)

            # Extract any document links from this row (main or sub-row)
            links = row.find_all("a", href=re.compile(r"SearchMedia\.aspx\?MediaVersionID=", re.I))
            for link in links:
                href = link.get("href", "")
                media_match = re.search(r"MediaVersionID=([a-f0-9-]+)", href, re.I)
                if not media_match:
                    continue

                media_id = media_match.group(1)
                if media_id in seen_media_ids:
                    continue
                seen_media_ids.add(media_id)

                # Get document type from DT parameter or link's sibling text
                dt_match = re.search(r"DT=([^&]+)", href)
                doc_type = dt_match.group(1).replace("+", " ") if dt_match else ""

                # Also get label from the cell next to the link (sub-rows)
                doc_label = ""
                parent_cell = link.find_parent("td")
                if parent_cell:
                    next_cell = parent_cell.find_next_sibling("td")
                    if next_cell:
                        doc_label = next_cell.get_text(strip=True)

                # Build a descriptive filename using the event context
                name_parts = []
                if current_date:
                    name_parts.append(current_date)
                if current_event:
                    name_parts.append(current_event)
                if current_desc:
                    name_parts.append(current_desc)
                # Append doc type if it adds info (e.g., "Brief" vs "Notice")
                if doc_label and doc_label.lower() not in current_event.lower():
                    name_parts.append(doc_label)
                elif doc_type and doc_type.lower() not in current_event.lower():
                    name_parts.append(doc_type)

                if not name_parts:
                    name_parts.append(f"document-{media_id[:8]}")

                filename = sanitize_filename(" - ".join(name_parts) + ".pdf")

                filings.append({
                    "media_version_id": media_id,
                    "date": current_date,
                    "event_type": current_event,
                    "description": current_desc,
                    "doc_type": doc_type or doc_label,
                    "filename": filename,
                    "source_url": urljoin(BASE_URL, href),
                })

    return filings
