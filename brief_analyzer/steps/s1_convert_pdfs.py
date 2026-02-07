"""Step 1: Convert PDFs to text (pdftotext with tesseract fallback)."""

from pathlib import Path

from ..config import ProjectConfig
from ..utils.pdf_utils import pdf_to_text
from ..utils.file_utils import find_briefs


def run(config: ProjectConfig):
    """Convert all PDFs in the project directory to text."""
    pdfs = find_briefs(config.project_dir)

    if not pdfs:
        print("No PDF files found in project directory.")
        return

    converted = 0
    skipped = 0

    for pdf_path in pdfs:
        txt_path = pdf_path.with_suffix(".txt")

        if txt_path.exists() and txt_path.stat().st_size > 0:
            print(f"  Skipping (already exists): {txt_path.name}")
            skipped += 1
            continue

        print(f"  Converting: {pdf_path.name}")
        success = pdf_to_text(pdf_path, txt_path)
        if success:
            size = txt_path.stat().st_size
            print(f"    -> {txt_path.name} ({size:,} bytes)")
            converted += 1
        else:
            print(f"    FAILED: Could not extract text from {pdf_path.name}")

    print(f"\nConverted {converted} PDFs, skipped {skipped} (already exist).")
