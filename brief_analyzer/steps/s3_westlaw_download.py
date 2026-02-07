"""Step 3: Semi-automated Westlaw download via Playwright.

The user must click 'Sign In' and 'Search' buttons manually.
Everything else (filling fields, navigating) is automated.

When run interactively (TTY), prompts the user to press Enter.
When run non-interactively, waits for file changes in the download dir.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from ..config import ProjectConfig
from ..utils.citation_parser import extract_ci_searches

# CSS selectors -- isolated here for easy updating when Westlaw changes its UI.
# Each uses comma-separated alternatives targeting data-testid, id, and aria-label.
SELECTORS = {
    "search_box": (
        '#searchInputId, '
        '[data-testid="searchInput"], '
        'input[aria-label="Search"], '
        '#co_searchInput'
    ),
    "search_button": (
        '#searchButton, '
        '[data-testid="searchButton"], '
        'button[aria-label="Search"]'
    ),
    "select_all_checkbox": (
        '#selectAllCheckbox, '
        '[data-testid="selectAllCheckbox"], '
        'input[aria-label="Select All"]'
    ),
    "download_button": (
        '#deliveryButton, '
        '[data-testid="deliveryButton"], '
        'button[aria-label="Download"]'
    ),
    "delivery_format_rtf": (
        'option[value="Rtf"], '
        '[data-testid="formatRtf"]'
    ),
    "username_input": (
        '#Username, '
        '#signInUserName, '
        'input[name="Username"], '
        'input[type="email"]'
    ),
    "password_input": (
        '#Password, '
        '#signInPassword, '
        'input[name="Password"], '
        'input[type="password"]'
    ),
    "client_matter_input": (
        '#clientIdTextbox, '
        '[data-testid="clientMatterInput"], '
        'input[aria-label*="Client"]'
    ),
}


def _is_interactive() -> bool:
    """Check if stdin is a real TTY (interactive terminal)."""
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _wait_for_user(prompt: str, download_dir: Path = None, timeout: int = 300):
    """Wait for user acknowledgement.

    In interactive mode: prompts for Enter.
    In non-interactive mode: watches download_dir for new files, or waits timeout.
    """
    if _is_interactive():
        input(prompt)
        return

    # Non-interactive: watch for new files in download_dir
    if download_dir:
        before = set(download_dir.iterdir()) if download_dir.exists() else set()
        print(f"  (non-interactive) Watching {download_dir} for new files... (timeout {timeout}s)")
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            current = set(download_dir.iterdir()) if download_dir.exists() else set()
            new_files = current - before
            # Ignore partial downloads (.crdownload, .part, etc.)
            completed = [f for f in new_files if not f.suffix in (".crdownload", ".part", ".tmp")]
            if completed:
                print(f"  Detected {len(completed)} new file(s): {[f.name for f in completed]}")
                time.sleep(2)  # Wait a bit for file to finish writing
                return
        print(f"  Timeout waiting for downloads.")
    else:
        print(f"  (non-interactive) Waiting 30 seconds...")
        time.sleep(30)


def run(config: ProjectConfig):
    """Launch Playwright browser for semi-automated Westlaw downloads."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "Playwright is required for Westlaw downloads.\n"
            "Install: pip install playwright && python -m playwright install chromium"
        )

    # Parse ci() searches from AUTHORITIES.md
    auth_path = config.project_dir / "AUTHORITIES.md"
    if not auth_path.exists():
        raise FileNotFoundError("AUTHORITIES.md not found. Run the 'authorities' step first.")

    auth_text = auth_path.read_text()
    ci_searches = extract_ci_searches(auth_text)

    print(f"  Found {len(ci_searches)} ci() search group(s)")

    # Filter out citations already downloaded (from CourtListener or previous runs)
    ci_searches = _filter_ci_searches(
        ci_searches,
        config.project_dir / "COURTLISTENER_RESULTS.json",
        config.authorities_dir,
    )
    if not ci_searches:
        print("  All citations already downloaded. Skipping Westlaw.")
        return

    download_dir = config.authorities_dir

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()

        # Step 1: Login
        _do_login(page, config)

        # Step 2: Client/matter dialog
        _handle_client_matter(page, config)

        # Step 3: ci() searches (all citations go through ci())
        print("\n  NOTE: Set the Westlaw data source to 'All State & Federal' before searching.")
        for i, search in enumerate(ci_searches, 1):
            print(f"\n--- ci() search {i}/{len(ci_searches)} ---")
            _do_ci_search(page, search, download_dir)

        # Summary
        rtf_count = len(list(download_dir.glob("*.rtf"))) + len(list(download_dir.glob("*.RTF")))
        print(f"\n{'='*50}")
        print(f"Download complete. {rtf_count} RTF files in {download_dir}")
        print(f"{'='*50}")

        _wait_for_user("\nPress Enter to close the browser...")
        browser.close()


def _do_login(page, config: ProjectConfig):
    """Navigate to login page and wait for user to authenticate."""
    login_url = config.westlaw.login_url
    print(f"  Navigating to: {login_url}")
    page.goto(login_url, timeout=60000)

    # Wait for either the Thomson Reuters sign-on page or Westlaw itself
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    # Check if we're already logged in (redirected to Westlaw)
    if "next.westlaw.com" in page.url and "signon" not in page.url.lower():
        print("  Already logged in.")
        return

    # We should be on signon.thomsonreuters.com or similar
    print(f"  Login page: {page.url[:80]}")

    # Fill credentials if provided
    if config.westlaw.username:
        try:
            username_el = page.locator(SELECTORS["username_input"]).first
            username_el.fill(config.westlaw.username, timeout=5000)
        except Exception:
            pass

    if config.westlaw.password:
        try:
            password_el = page.locator(SELECTORS["password_input"]).first
            password_el.fill(config.westlaw.password, timeout=5000)
        except Exception:
            pass

    print(">>> Please log in to Westlaw in the browser window.")
    # Wait for redirect to next.westlaw.com (up to 3 minutes for MFA, etc.)
    try:
        page.wait_for_url("**next.westlaw.com/**", timeout=180000)
        print("  Login successful.")
    except Exception:
        # Check if we're on westlaw at all
        if "westlaw.com" in page.url:
            print("  Appears to be logged in.")
        else:
            print("  Login timeout. Continuing -- you may need to log in manually.")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def _handle_client_matter(page, config: ProjectConfig):
    """Fill client/matter dialog if it appears."""
    if not config.westlaw.client_matter:
        return

    time.sleep(2)
    try:
        cm_el = page.locator(SELECTORS["client_matter_input"]).first
        if cm_el.is_visible(timeout=5000):
            cm_el.fill(config.westlaw.client_matter)
            print(f"  Filled client/matter: {config.westlaw.client_matter}")
            print(">>> Please confirm the client/matter dialog.")
            time.sleep(3)
    except Exception:
        pass  # Dialog may not appear


def _do_ci_search(page, search_term: str, download_dir: Path):
    """Run a ci() search and download results as RTF."""
    # Navigate to main search if not there
    if "search/home" not in page.url.lower():
        try:
            page.goto("https://next.westlaw.com/search/home.html", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

    # Fill search box
    try:
        search_el = page.locator(SELECTORS["search_box"]).first
        search_el.click()
        search_el.fill(search_term)
        print(f"  Filled search: {search_term[:80]}...")
    except Exception as e:
        print(f"  Could not fill search box: {e}")
        print("  Please paste the search manually:")
        print(f"  {search_term}")

    print(">>> Please click 'Search' in the browser.")
    # Wait for results page
    try:
        page.wait_for_url("**/search/**", timeout=120000)
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        print("  Timeout waiting for results. Please complete the search manually.")

    # Try to select all and download
    _download_results(page, download_dir)


def _download_results(page, download_dir: Path):
    """Attempt to select all results and download as RTF."""
    print("  Attempting to download results...")
    print("  If automatic download fails, please download manually as RTF.")
    print(f"  Save to: {download_dir}")

    # Try select all
    try:
        select_all = page.locator(SELECTORS["select_all_checkbox"]).first
        if select_all.is_visible(timeout=5000):
            select_all.click()
            time.sleep(1)
    except Exception:
        print("  Could not auto-select results. Please select them manually.")

    # Try download
    try:
        dl_btn = page.locator(SELECTORS["download_button"]).first
        if dl_btn.is_visible(timeout=5000):
            dl_btn.click()
            time.sleep(2)
            # Select RTF format if dropdown appears
            try:
                rtf_opt = page.locator(SELECTORS["delivery_format_rtf"]).first
                if rtf_opt.is_visible(timeout=3000):
                    rtf_opt.click()
            except Exception:
                pass
    except Exception:
        print("  Could not auto-click download. Please download manually.")

    _wait_for_user("  Press Enter when download is complete...", download_dir)


def _filter_ci_searches(
    ci_searches: list[str],
    results_path: Path,
    auth_dir: Path,
) -> list[str]:
    """Remove citations from ci() searches that are already downloaded.

    Checks COURTLISTENER_RESULTS.json and existing .txt files in authorities/.
    Returns filtered ci() strings, dropping any that become empty.
    """
    # Collect all citation strings that are already available
    have_cites = set()

    # From CourtListener results
    if results_path.exists():
        try:
            data = json.loads(results_path.read_text())
            for entry in data.get("found", []):
                # Extract volume/reporter/page citations from the entry text
                for m in re.finditer(
                    r'(\d+)\s+'
                    r'(S\.W\.(?:2d|3d)|F\.(?:2d|3d|4th)|F\.\s*App\'x|F\.\s*Supp\.(?:\s*2d)?|'
                    r'U\.S\.|S\.\s*Ct\.|L\.\s*Ed\.(?:\s*2d)?)'
                    r'\s+(\d+)',
                    entry,
                ):
                    have_cites.add(f"{m.group(1)} {m.group(2)} {m.group(3)}")
                # Extract WL cites
                for m in re.finditer(r'(\d{4})\s+WL\s+(\d+)', entry):
                    have_cites.add(f"{m.group(1)} WL {m.group(2)}")
        except (json.JSONDecodeError, KeyError):
            pass

    # From existing .txt files in authorities/
    for f in auth_dir.glob("*.txt"):
        fname = f.name
        for m in re.finditer(
            r'(\d+)\s+'
            r'(S\.W\.(?:2d|3d)|F\.(?:2d|3d|4th)|F\.\s*App\'x|F\.\s*Supp\.(?:\s*2d)?|'
            r'U\.S\.|S\.\s*Ct\.|L\.\s*Ed\.(?:\s*2d)?)'
            r'\s+(\d+)',
            fname,
        ):
            have_cites.add(f"{m.group(1)} {m.group(2)} {m.group(3)}")
        for m in re.finditer(r'(\d{4})\s+WL\s+(\d+)', fname):
            have_cites.add(f"{m.group(1)} WL {m.group(2)}")

    if not have_cites:
        return ci_searches

    # Filter each ci() block
    filtered = []
    for ci_str in ci_searches:
        # Extract the inner content of ci(...)
        inner_match = re.match(r'ci\((.+)\)', ci_str)
        if not inner_match:
            filtered.append(ci_str)
            continue

        inner = inner_match.group(1)
        # Parse quoted citations: "845 S.W.2d 874" "810 S.W.2d 372" ...
        quotes = re.findall(r'"([^"]+)"', inner)

        remaining = []
        removed = 0
        for q in quotes:
            # Check if this quoted citation matches something we already have
            # The ci() format uses compact reporters (S.W.2d) while filenames
            # may use the same format
            if any(q in have or have in q for have in have_cites):
                removed += 1
            else:
                remaining.append(q)

        if not remaining:
            print(f"  ci() block fully covered ({removed} citations already downloaded)")
            continue

        if removed:
            print(f"  Removed {removed} already-downloaded citations from ci() block")

        # Rebuild ci() string
        new_ci = 'ci(' + ' '.join(f'"{r}"' for r in remaining) + ')'
        filtered.append(new_ci)

    return filtered


