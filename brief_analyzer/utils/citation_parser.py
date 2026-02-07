"""Texas citation regex extraction from AUTHORITIES.md and text files."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Citation:
    """A parsed legal citation."""
    case_name: str
    volume: str
    reporter: str
    page: str
    court: str = ""
    year: str = ""
    disposition: str = ""
    wl_cite: str = ""
    ci_search: str = ""

    @property
    def full_cite(self) -> str:
        """Full citation string for filename."""
        parts = [f"{self.case_name}, {self.volume} {self.reporter} {self.page}"]
        if self.court or self.year:
            paren = []
            if self.court:
                paren.append(self.court)
            if self.year:
                paren.append(self.year)
            if self.disposition:
                paren.append(self.disposition)
            parts.append(f"({', '.join(paren)})")
        return " ".join(parts)


# Matches: Name v. Name, 123 S.W.3d 456
REPORTER_CITE_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z\s.']+?)\s*v\.\s*"
    r"(?P<name2>[A-Z][A-Za-z\s.']+?),\s*"
    r"(?P<vol>\d+)\s+"
    r"(?P<reporter>S\.W\.(?:2d|3d)|U\.S\.|S\.\s*Ct\.|L\.\s*Ed\.(?:\s*2d)?)\s+"
    r"(?P<page>\d+)"
)

# Matches: 2016 WL 3199027
WL_CITE_RE = re.compile(r"(?P<year>\d{4})\s+WL\s+(?P<number>\d+)")

# Matches the entire ci(...) block, which may span a single line
# Format: ci("845 S.W.2d 874" "810 S.W.2d 372" ...)
CI_BLOCK_RE = re.compile(r'ci\(([^)]+)\)')


def extract_ci_searches(text: str) -> list[str]:
    """Extract ci() search strings from AUTHORITIES.md content.

    Returns the full ci(...) string for each block found, ready to paste
    into Westlaw's search box.
    """
    results = []
    for match in CI_BLOCK_RE.finditer(text):
        # Reconstruct the full ci() string
        full = f"ci({match.group(1)})"
        results.append(full)
    return results


def extract_reporter_cites(text: str) -> list[str]:
    """Extract reporter citations (e.g., '259 S.W.3d 778') from text."""
    matches = REPORTER_CITE_RE.findall(text)
    results = []
    for m in matches:
        results.append(f"{m[2]} {m[3]} {m[4]}")
    return results


def parse_case_from_text(text: str) -> Optional[Citation]:
    """Parse citation info from the first ~2000 chars of a case text file.

    Looks for the case caption, reporter citation, court, and year.
    """
    header = text[:3000]

    # Find party names from "v." pattern
    v_match = re.search(
        r"^(.+?)\s*[,\n]\s*(?:Appellant|Appellee|Petitioner|Respondent|Plaintiff|Defendant)?"
        r".*?\bv\.\s*(.+?)(?:\s*[,\n]|$)",
        header, re.MULTILINE | re.IGNORECASE
    )
    case_name = ""
    if v_match:
        p1 = v_match.group(1).strip().rstrip(",")
        p2 = v_match.group(2).strip().rstrip(",")
        # Clean up party names
        for prefix in ("STATE OF TEXAS", "THE STATE OF TEXAS"):
            if p2.upper().startswith(prefix):
                p2 = "State"
        case_name = f"{p1} v. {p2}"

    # Find reporter citation
    cite_match = re.search(
        r"(\d+)\s+(S\.W\.(?:2d|3d)|U\.S\.)\s+(\d+)", header
    )
    volume, reporter, page = "", "", ""
    if cite_match:
        volume = cite_match.group(1)
        reporter = cite_match.group(2)
        page = cite_match.group(3)

    # Find WL citation
    wl_match = WL_CITE_RE.search(header)
    wl_cite = ""
    if wl_match:
        wl_cite = f"{wl_match.group('year')} WL {wl_match.group('number')}"

    # Find court
    court = ""
    court_patterns = [
        (r"Court\s+of\s+Criminal\s+Appeals", "Tex. Crim. App."),
        (r"Supreme\s+Court\s+of\s+Texas", "Tex."),
        (r"Court\s+of\s+Appeals.*?Houston.*?First", "Tex. App.--Houston [1st Dist.]"),
        (r"Court\s+of\s+Appeals.*?Houston.*?Fourteenth", "Tex. App.--Houston [14th Dist.]"),
        (r"Court\s+of\s+Appeals.*?Houston.*?14th", "Tex. App.--Houston [14th Dist.]"),
        (r"Court\s+of\s+Appeals.*?Dallas", "Tex. App.--Dallas"),
        (r"Court\s+of\s+Appeals.*?Fort\s+Worth", "Tex. App.--Fort Worth"),
        (r"Court\s+of\s+Appeals.*?San\s+Antonio", "Tex. App.--San Antonio"),
        (r"Court\s+of\s+Appeals.*?Austin", "Tex. App.--Austin"),
        (r"Court\s+of\s+Appeals.*?Waco", "Tex. App.--Waco"),
        (r"Court\s+of\s+Appeals.*?Amarillo", "Tex. App.--Amarillo"),
        (r"Court\s+of\s+Appeals.*?El\s+Paso", "Tex. App.--El Paso"),
        (r"Court\s+of\s+Appeals.*?Texarkana", "Tex. App.--Texarkana"),
        (r"Court\s+of\s+Appeals.*?Beaumont", "Tex. App.--Beaumont"),
        (r"Court\s+of\s+Appeals.*?Tyler", "Tex. App.--Tyler"),
        (r"Court\s+of\s+Appeals.*?Eastland", "Tex. App.--Eastland"),
        (r"Court\s+of\s+Appeals.*?Corpus\s+Christi", "Tex. App.--Corpus Christi"),
        (r"Supreme\s+Court.*?United\s+States", "U.S."),
    ]
    for pattern, abbrev in court_patterns:
        if re.search(pattern, header, re.IGNORECASE):
            court = abbrev
            break

    # Find year from date
    year = ""
    year_match = re.search(r"(?:Decided|Filed|Delivered).*?(\d{4})", header)
    if year_match:
        year = year_match.group(1)
    elif wl_match:
        year = wl_match.group("year")

    # Find disposition
    disposition = ""
    disp_patterns = [
        (r"pet(?:ition)?\.?\s*ref(?:used)?'?d", "pet. ref'd"),
        (r"no\s+pet(?:ition)?", "no pet."),
        (r"cert\.\s*denied", "cert. denied"),
    ]
    for pattern, disp in disp_patterns:
        if re.search(pattern, header, re.IGNORECASE):
            disposition = disp
            break

    if not case_name and not volume:
        return None

    return Citation(
        case_name=case_name,
        volume=volume,
        reporter=reporter,
        page=page,
        court=court,
        year=year,
        disposition=disposition,
        wl_cite=wl_cite,
    )
