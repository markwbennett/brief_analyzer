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

    # Find RTF files (both .rtf and .RTF)
    rtfs = sorted(auth_dir.glob("*.rtf")) + sorted(auth_dir.glob("*.RTF"))
    if not rtfs:
        # Check if text files already exist (already processed)
        txts = list(auth_dir.glob("*.txt"))
        if txts:
            print(f"  No RTFs found but {len(txts)} .txt files exist. Already processed?")
            return
        print("  No RTF files found in authorities directory.")
        return

    print(f"  Found {len(rtfs)} RTF files to process.")

    converted = 0
    renamed = 0

    for rtf_path in rtfs:
        # Convert RTF to text using textutil (macOS)
        txt_path = rtf_path.with_suffix(".txt")
        if not txt_path.exists():
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

        if not txt_path.exists():
            print(f"  No text output for {rtf_path.name}")
            continue

        # Parse citation from text content
        text = txt_path.read_text(errors="replace")
        citation = parse_case_from_text(text)

        if citation and (citation.case_name or citation.volume):
            new_name = citation.full_cite + ".txt"
            new_name = sanitize_filename(new_name)
            new_path = auth_dir / new_name

            if new_path != txt_path:
                result = safe_rename(txt_path, new_path)
                print(f"  {rtf_path.name} -> {result.name}")
                renamed += 1
            else:
                print(f"  {txt_path.name} (name already correct)")
        else:
            print(f"  {rtf_path.name} -> {txt_path.name} (could not parse citation)")

        # Move RTF to rtf/ subdirectory
        rtf_dest = rtf_dir / rtf_path.name
        if not rtf_dest.exists():
            rtf_path.rename(rtf_dest)

    print(f"\n  Converted {converted} RTFs, renamed {renamed} files.")
    print(f"  RTF originals moved to: {rtf_dir}")
