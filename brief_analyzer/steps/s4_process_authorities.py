"""Step 4: Process downloaded authorities -- RTF to text, rename, organize."""

import re
import subprocess
from pathlib import Path

from ..config import ProjectConfig
from ..utils.citation_parser import parse_case_from_text
from ..utils.file_utils import sanitize_filename, safe_rename


def run(config: ProjectConfig):
    """Convert RTFs to text, parse citations, rename files."""
    auth_dir = config.authorities_dir
    rtf_dir = config.rtf_dir
    rtf_dir.mkdir(exist_ok=True)

    # Find RTF files in rtf/ subdirectory (where Westlaw downloads land)
    rtfs = sorted(rtf_dir.glob("*.rtf")) + sorted(rtf_dir.glob("*.RTF"))
    if not rtfs:
        print("  No RTF files found in authorities/rtf/. Nothing to process.")
        return

    print(f"  Found {len(rtfs)} RTF files to process.")

    converted = 0
    renamed = 0
    skipped = 0

    for rtf_path in rtfs:
        # Convert RTF to text using textutil (macOS).
        # textutil writes the .txt next to the .rtf (in rtf/).
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

        # Parse citation from text content
        text = txt_in_rtf_dir.read_text(errors="replace")
        citation = parse_case_from_text(text)

        if citation and (citation.case_name or citation.volume):
            new_name = sanitize_filename(citation.full_cite + ".txt")
        else:
            # Fall back to the RTF filename
            new_name = rtf_path.stem + ".txt"
            print(f"  {rtf_path.name}: could not parse citation, using original name")

        final_path = auth_dir / new_name

        # Skip if already exists in authorities/
        if final_path.exists():
            print(f"  {new_name} (already exists)")
            skipped += 1
            # Clean up the intermediate .txt in rtf/
            txt_in_rtf_dir.unlink(missing_ok=True)
            continue

        # Move .txt from rtf/ up to authorities/ with the citation-based name
        txt_in_rtf_dir.rename(final_path)
        print(f"  {rtf_path.name} -> {final_path.name}")
        renamed += 1

    print(f"\n  Converted {converted} RTFs, renamed {renamed} files, skipped {skipped} (already exist).")
    print(f"  RTF originals remain in: {rtf_dir}")
