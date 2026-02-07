"""PDF conversion utilities: pdftotext with tesseract fallback."""

import subprocess
import tempfile
from pathlib import Path


def pdf_to_text(pdf_path: Path, output_path: Path) -> bool:
    """Convert PDF to text. Returns True if successful.

    Uses pdftotext -layout first. If output is too short (<100 chars),
    falls back to pdftoppm + tesseract for scanned documents.
    """
    # Try pdftotext first
    try:
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(output_path)],
            check=True,
            capture_output=True,
        )
        # Check if we got meaningful output
        if output_path.exists() and len(output_path.read_text(errors="replace")) >= 100:
            return True
    except subprocess.CalledProcessError:
        pass

    # Fallback: OCR via pdftoppm + tesseract
    print(f"  pdftotext produced minimal output; falling back to OCR for {pdf_path.name}")
    return _ocr_pdf(pdf_path, output_path)


def _ocr_pdf(pdf_path: Path, output_path: Path) -> bool:
    """OCR a PDF using pdftoppm + tesseract."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Convert PDF pages to images
        try:
            subprocess.run(
                ["pdftoppm", "-r", "300", "-png", str(pdf_path), str(tmp / "page")],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"  pdftoppm failed: {e.stderr.decode()}")
            return False

        # OCR each page image
        page_images = sorted(tmp.glob("page-*.png"))
        if not page_images:
            print(f"  No page images produced for {pdf_path.name}")
            return False

        all_text = []
        for img in page_images:
            try:
                result = subprocess.run(
                    ["tesseract", str(img), "stdout"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                all_text.append(result.stdout)
            except subprocess.CalledProcessError as e:
                print(f"  tesseract failed on {img.name}: {e.stderr}")

        if all_text:
            output_path.write_text("\n\n".join(all_text))
            return True

    return False
