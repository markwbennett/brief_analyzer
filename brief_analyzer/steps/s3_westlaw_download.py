"""Step 3: Semi-automated Westlaw download via Playwright.

The user must click 'Sign In' and 'Search' buttons manually.
Everything else (filling fields, navigating) is automated.

When run interactively (TTY), prompts the user to press Enter.
When run non-interactively, waits for file changes in the download dir.
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

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
        '#co_searchHeader_selectAll'
    ),
    "download_button": (
        '#deliveryLinkButton1'
    ),
    "delivery_format_fulltext": (
        '#co_delivery_format_fulltext'
    ),
    "delivery_file_container": (
        '#co_delivery_fileContainer'
    ),
    "delivery_download_submit": (
        '#co_deliveryDownloadButton'
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


def _save_download(download, dest_dir: Path):
    """Save a Playwright download to the destination directory."""
    filename = download.suggested_filename
    save_path = dest_dir / filename
    print(f"  Downloading: {filename}")
    download.save_as(str(save_path))
    print(f"  Saved: {save_path.name} ({save_path.stat().st_size:,} bytes)")


def _collect_chromium_downloads(chromium_dl_dir: Path, dest_dir: Path):
    """Move files from Chromium's download dir to the rtf/ directory.

    Westlaw delivers downloads as hex-named files with no extension.
    We detect ZIPs by magic bytes and rename/unzip accordingly.
    """
    import shutil
    import zipfile

    if not chromium_dl_dir.exists():
        return

    for f in chromium_dl_dir.iterdir():
        if not f.is_file() or f.name.startswith("."):
            continue

        # Check if it's a ZIP (magic bytes PK\x03\x04)
        try:
            with open(f, "rb") as fh:
                magic = fh.read(4)
        except OSError:
            continue

        if magic[:4] == b"PK\x03\x04":
            # It's a ZIP — extract RTFs directly into dest_dir
            print(f"  Unpacking ZIP: {f.name}")
            try:
                with zipfile.ZipFile(f) as zf:
                    rtf_count = 0
                    for member in zf.namelist():
                        # Skip directories and hidden files
                        basename = Path(member).name
                        if not basename or basename.startswith("."):
                            continue
                        # Extract flat (ignore subdirectory structure)
                        target = dest_dir / basename
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        rtf_count += 1
                    print(f"    Extracted {rtf_count} file(s)")
            except zipfile.BadZipFile:
                print(f"  Warning: {f.name} looked like ZIP but is corrupt, copying as-is")
                shutil.copy2(f, dest_dir / f"{f.name}.zip")
        else:
            # Not a ZIP — copy as-is (might be a single RTF)
            dest = dest_dir / f.name
            if not f.suffix:
                dest = dest_dir / f"{f.name}.rtf"
            shutil.copy2(f, dest)
            print(f"  Copied: {dest.name}")


def _is_interactive() -> bool:
    """Check if stdin is a real TTY (interactive terminal)."""
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


# Directories to watch for Westlaw downloads (ZIP or RTF files)
_DOWNLOAD_WATCH_DIRS = [
    Path.home() / "Downloads",
]

# File extensions that indicate a Westlaw download
_DOWNLOAD_EXTENSIONS = {".zip", ".rtf", ".RTF"}

# Extensions that indicate an incomplete download
_PARTIAL_EXTENSIONS = {".crdownload", ".part", ".tmp"}


def _wait_for_user(prompt: str, download_dir: Path = None,
                   chromium_dl_dir: Path = None, timeout: int = 300):
    """Wait for user acknowledgement.

    In interactive mode: prompts for Enter.
    In non-interactive mode: watches the rtf dir, Chromium's download dir,
    and ~/Downloads for new files, continuing automatically when detected.
    Westlaw delivers files as hex-named blobs (no extension) so we watch
    for ANY new file, not just .zip/.rtf.
    """
    if _is_interactive():
        input(prompt)
        return

    # Build list of directories to watch
    watch_dirs = []
    if download_dir and download_dir.exists():
        watch_dirs.append(download_dir)
    if chromium_dl_dir and chromium_dl_dir.exists():
        watch_dirs.append(chromium_dl_dir)
    for d in _DOWNLOAD_WATCH_DIRS:
        if d.exists() and d not in watch_dirs:
            watch_dirs.append(d)

    # Snapshot current state of all watch dirs
    snapshots = {}
    for d in watch_dirs:
        snapshots[d] = set(d.iterdir())

    print(f"  {prompt} (timeout {timeout}s)")
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        for d in watch_dirs:
            if not d.exists():
                continue
            current = set(d.iterdir())
            new_files = current - snapshots[d]
            # Accept any new file -- Westlaw uses hex names with no extension
            completed = [
                f for f in new_files
                if f.is_file()
                and f.suffix not in _PARTIAL_EXTENSIONS
                and not f.name.startswith(".")
            ]
            if completed:
                names = [f.name[:40] for f in completed]
                print(f"  Detected {len(completed)} new file(s) in {d.name}/: {names}")
                # Wait for file to finish writing
                time.sleep(5)
                return
    print(f"  Timeout waiting for downloads.")


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
    ci_blocks = extract_ci_searches(auth_text)

    # Merge all ci() blocks into a flat list of quoted citations
    all_cites = _merge_ci_blocks(ci_blocks)
    print(f"  Found {len(all_cites)} total citation(s) across {len(ci_blocks)} ci() block(s)")

    # Filter out citations already downloaded (from CourtListener or previous runs)
    remaining = _filter_citations(
        all_cites,
        config.project_dir / "COURTLISTENER_RESULTS.json",
        config.authorities_dir,
    )
    if not remaining:
        print("  All citations already downloaded. Skipping Westlaw.")
        return

    print(f"  {len(remaining)} citation(s) still needed from Westlaw")

    # Split into equal groups of <50
    ci_searches = _split_into_groups(remaining)
    print(f"  Split into {len(ci_searches)} group(s)")

    download_dir = config.rtf_dir
    download_dir.mkdir(parents=True, exist_ok=True)

    # Chromium profile download dir -- Westlaw delivers as hex-named files
    # that land here via the browser's built-in download manager.
    import tempfile
    chromium_dl_dir = Path(tempfile.mkdtemp(prefix="westlaw_dl_"))

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            downloads_path=str(chromium_dl_dir),
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        page.on("download", lambda dl: _save_download(dl, download_dir))

        # Step 1: Login
        _do_login(page, config)

        # Step 2: Client/matter dialog
        _handle_client_matter(page, config)

        # Step 3: ci() searches (all citations go through ci())
        for i, search in enumerate(ci_searches, 1):
            print(f"\n--- ci() search {i}/{len(ci_searches)} ---")
            _do_ci_search(page, search, download_dir, chromium_dl_dir)

        # Collect any downloads from Chromium's download dir (hex-named ZIPs)
        _collect_chromium_downloads(chromium_dl_dir, download_dir)

        # Summary
        rtf_count = len(list(download_dir.glob("*.rtf"))) + len(list(download_dir.glob("*.RTF")))
        zip_count = len(list(download_dir.glob("*.zip")))
        total = rtf_count + zip_count
        print(f"\n{'='*50}")
        print(f"Download complete. {total} file(s) in {download_dir}")
        if zip_count:
            print(f"  ({zip_count} ZIP file(s) to unpack in process step)")
        print(f"{'='*50}")

        browser.close()


def _fill_credentials_on_page(target_page, config: ProjectConfig) -> bool:
    """Fill username/password on a page. Returns True if both fields were filled."""
    filled = False
    if config.westlaw.username:
        try:
            username_el = target_page.locator(SELECTORS["username_input"]).first
            username_el.fill(config.westlaw.username, timeout=5000)
            filled = True
            print(f"  Filled username: {config.westlaw.username}")
        except Exception:
            pass

    if config.westlaw.password:
        try:
            password_el = target_page.locator(SELECTORS["password_input"]).first
            password_el.fill(config.westlaw.password, timeout=5000)
            print("  Filled password.")
        except Exception:
            filled = False

    if filled:
        try:
            sign_in_btn = target_page.locator(
                '#SignInButton, '
                'button:has-text("Sign In"), '
                'input[type="submit"][value*="Sign"], '
                '#btnSignIn'
            ).first
            sign_in_btn.click(timeout=5000)
            print("  Submitted login form.")
        except Exception:
            try:
                password_el = target_page.locator(SELECTORS["password_input"]).first
                password_el.press("Enter")
                print("  Pressed Enter to submit login.")
            except Exception:
                print("  Could not auto-submit. Please click Sign In manually.")
    return filled


def _do_login(page, config: ProjectConfig):
    """Navigate to login page and wait for user to authenticate.

    Thomson Reuters SSO may open a popup window for credentials.
    We watch for popups and fill credentials there too.
    """
    login_url = config.westlaw.login_url
    context = page.context

    # Track popup pages for credential filling
    def _on_popup(popup_page):
        print(f"  Detected sign-in popup: {popup_page.url[:80]}")
        try:
            popup_page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        _fill_credentials_on_page(popup_page, config)

    context.on("page", _on_popup)

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

    # Try filling credentials on the main page first
    filled = _fill_credentials_on_page(page, config)
    if not filled:
        print(">>> Please log in to Westlaw in the browser window.")

    # Thomson Reuters sometimes redirects to a separate password page
    # after submitting the username. Watch for it and fill password there.
    if filled and config.westlaw.password:
        try:
            page.wait_for_url("**/u/login/password**", timeout=8000)
            print(f"  Redirected to password page: {page.url[:80]}")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            pw_el = page.locator(SELECTORS["password_input"]).first
            pw_el.fill(config.westlaw.password, timeout=5000)
            print("  Filled password on second page.")
            try:
                sign_in_btn = page.locator(
                    'button:has-text("Sign in"), '
                    'button:has-text("Sign In"), '
                    'input[type="submit"]'
                ).first
                sign_in_btn.click(timeout=5000)
                print("  Submitted password form.")
            except Exception:
                try:
                    pw_el.press("Enter")
                    print("  Pressed Enter to submit password.")
                except Exception:
                    print("  Could not auto-submit password page. Please click Sign In.")
        except Exception:
            pass  # No redirect to password page -- first page worked or user is handling it

    # Wait for redirect to next.westlaw.com (up to 3 minutes for MFA, popup, etc.)
    try:
        page.wait_for_url("**next.westlaw.com/**", timeout=180000)
        print("  Login successful.")
    except Exception:
        # Check all pages in context — login may have completed on a different page
        for p in context.pages:
            if "next.westlaw.com" in p.url and "signon" not in p.url.lower():
                print("  Login successful (via popup).")
                # Switch to the logged-in page if it's not the main one
                if p != page:
                    p.bring_to_front()
                break
        else:
            if "westlaw.com" in page.url:
                print("  Appears to be logged in.")
            else:
                print("  Login timeout. Continuing -- you may need to log in manually.")

    # Remove popup handler to avoid interfering with later popups
    try:
        context.remove_listener("page", _on_popup)
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    _delay()

    # Handle Client ID / Continue interstitial page
    _handle_continue_page(page)


def _delay(lo: float = 1.0, hi: float = 3.0):
    """Random delay to account for slow page loading."""
    time.sleep(random.uniform(lo, hi))


def _handle_continue_page(page):
    """Click 'Continue' on the Client ID interstitial page if it appears."""
    try:
        continue_btn = page.locator(
            'input[value="Continue"], '
            'button:has-text("Continue")'
        ).first
        if continue_btn.is_visible(timeout=5000):
            print("  Client ID page detected. Clicking Continue...")
            _delay(0.5, 1.5)
            continue_btn.click()
            _delay()
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            print(f"  Continued to: {page.url[:80]}")
    except Exception:
        pass  # No Continue page -- already on main Westlaw


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


def _do_ci_search(page, search_term: str, download_dir: Path, chromium_dl_dir: Path):
    """Run a ci() search and download results as RTF."""
    # Build results URL directly -- no need to fill search box or click Search
    encoded_query = quote(f"adv: {search_term}")
    results_url = (
        f"https://next.westlaw.com/Search/Results.html"
        f"?query={encoded_query}"
        f"&jurisdiction=ALLCASES"
        f"&contentType=CASE"
        f"&transitionType=Search"
        f"&contextData=%28sc.Default%29"
    )
    print(f"  Navigating directly to search results...")
    _delay()
    page.goto(results_url, timeout=60000)

    # Wait for results to render (Select All checkbox appears when ready)
    try:
        select_all = page.locator(SELECTORS["select_all_checkbox"]).first
        select_all.wait_for(state="visible", timeout=30000)
        select_all.click()
        print("  Clicked 'Select All'.")
        _delay(1.0, 2.0)
    except Exception as e:
        print(f"  Could not click Select All: {e}")

    # Click download icon to open delivery dialog
    try:
        dl_btn = page.locator(SELECTORS["download_button"]).first
        dl_btn.wait_for(state="visible", timeout=10000)
        dl_btn.click()
        print("  Clicked download icon. Waiting for delivery dialog...")
        _delay(2.0, 4.0)

        # Ensure format is RTF and container is ZIP (they default to this, but be safe)
        try:
            fmt_select = page.locator(SELECTORS["delivery_format_fulltext"]).first
            if fmt_select.is_visible(timeout=5000):
                fmt_select.select_option("Rtf")
                _delay(0.5, 1.0)
        except Exception:
            pass
        try:
            container_select = page.locator(SELECTORS["delivery_file_container"]).first
            if container_select.is_visible(timeout=3000):
                container_select.select_option("MultipleFileZip")
                _delay(0.5, 1.0)
        except Exception:
            pass

        # Click the Download submit button in the dialog
        submit_btn = page.locator(SELECTORS["delivery_download_submit"]).first
        submit_btn.wait_for(state="visible", timeout=10000)
        submit_btn.click()
        print("  Clicked 'Download' in delivery dialog.")
        _delay(2.0, 4.0)
    except Exception as e:
        print(f"  Could not auto-download: {e}")

    # Wait for download files to arrive
    _wait_for_user("  Waiting for download to complete...", download_dir, chromium_dl_dir)



def _merge_ci_blocks(ci_blocks: list[str]) -> list[str]:
    """Merge all ci() blocks into a flat, deduplicated list of quoted citations."""
    seen = set()
    result = []
    for ci_str in ci_blocks:
        inner_match = re.match(r'ci\((.+)\)', ci_str)
        if not inner_match:
            continue
        for q in re.findall(r'"([^"]+)"', inner_match.group(1)):
            if q not in seen:
                seen.add(q)
                result.append(q)
    return result


def _get_downloaded_cites(results_path: Path, auth_dir: Path) -> set[str]:
    """Collect citation strings already available from CourtListener or disk."""
    have_cites = set()

    # From CourtListener results
    if results_path.exists():
        try:
            data = json.loads(results_path.read_text())
            for entry in data.get("found", []):
                for m in re.finditer(
                    r'(\d+)\s+'
                    r'(S\.W\.(?:2d|3d)|F\.(?:2d|3d|4th)|F\.\s*App\'x|F\.\s*Supp\.(?:\s*2d)?|'
                    r'U\.S\.|S\.\s*Ct\.|L\.\s*Ed\.(?:\s*2d)?)'
                    r'\s+(\d+)',
                    entry,
                ):
                    have_cites.add(f"{m.group(1)} {m.group(2)} {m.group(3)}")
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

    return have_cites


def _filter_citations(
    all_cites: list[str],
    results_path: Path,
    auth_dir: Path,
) -> list[str]:
    """Remove citations already downloaded. Returns the remaining list."""
    have_cites = _get_downloaded_cites(results_path, auth_dir)
    if not have_cites:
        return all_cites

    remaining = []
    removed = 0
    for q in all_cites:
        if any(q in have or have in q for have in have_cites):
            removed += 1
        else:
            remaining.append(q)

    if removed:
        print(f"  Removed {removed} already-downloaded citation(s)")

    return remaining


def _split_into_groups(cites: list[str], max_per_group: int = 49) -> list[str]:
    """Split citations into equal-sized groups, each under max_per_group.

    Uses math.ceil(n / max_per_group) groups so that group sizes are as
    equal as possible and every group has < 50 citations.
    """
    import math
    n = len(cites)
    if n <= max_per_group:
        return ['ci(' + ' '.join(f'"{c}"' for c in cites) + ')']

    num_groups = math.ceil(n / max_per_group)
    base_size = n // num_groups
    remainder = n % num_groups

    groups = []
    idx = 0
    for i in range(num_groups):
        # Distribute remainder across the first groups
        size = base_size + (1 if i < remainder else 0)
        chunk = cites[idx:idx + size]
        groups.append('ci(' + ' '.join(f'"{c}"' for c in chunk) + ')')
        idx += size

    return groups


