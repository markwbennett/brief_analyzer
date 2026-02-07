"""Step 8: Generate PDFs from markdown using pandoc + xelatex."""

import subprocess
from pathlib import Path

from ..config import ProjectConfig

# Markdown files to convert to PDF
TARGET_FILES = [
    "CITECHECK.md",
    "ISSUE_ANALYSIS.md",
    "MOOT_QA.md",
]


def run(config: ProjectConfig):
    """Generate PDFs from markdown output files."""
    pc = config.pandoc

    generated = 0
    for md_name in TARGET_FILES:
        md_path = config.project_dir / md_name
        pdf_path = md_path.with_suffix(".pdf")

        if not md_path.exists():
            print(f"  Skipping (source not found): {md_name}")
            continue

        if pdf_path.exists() and pdf_path.stat().st_mtime >= md_path.stat().st_mtime:
            print(f"  Skipping (PDF newer than source): {pdf_path.name}")
            continue

        print(f"  Generating: {pdf_path.name}")

        cmd = [
            "pandoc",
            str(md_path),
            "-o", str(pdf_path),
            "--pdf-engine=xelatex",
            f"-V", f"mainfont={pc.font}",
            f"-V", f"sansfont={pc.heading_font}",
            f"-V", f"fontsize={pc.font_size}pt",
            f"-V", f"geometry:margin={pc.margins}",
            f"-V", f"documentclass={pc.document_class}",
            # Use sans font for headings
            "--include-in-header=/dev/stdin",
        ]

        # LaTeX header to use heading font for sections
        latex_header = (
            r"\usepackage{titlesec}"
            "\n"
            r"\titleformat{\section}{\Large\sffamily\bfseries}{\thesection}{1em}{}"
            "\n"
            r"\titleformat{\subsection}{\large\sffamily\bfseries}{\thesubsection}{1em}{}"
            "\n"
            r"\titleformat{\subsubsection}{\normalsize\sffamily\bfseries}{\thesubsubsection}{1em}{}"
            "\n"
        )

        try:
            result = subprocess.run(
                cmd,
                input=latex_header,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                print(f"    pandoc failed: {result.stderr[:500]}")

                # Fallback: try without custom fonts
                print(f"    Retrying with Courier fallback...")
                cmd_fallback = [
                    "pandoc",
                    str(md_path),
                    "-o", str(pdf_path),
                    "--pdf-engine=xelatex",
                    f"-V", f"mainfont=Courier",
                    f"-V", f"fontsize={pc.font_size}pt",
                    f"-V", f"geometry:margin={pc.margins}",
                    f"-V", f"documentclass={pc.document_class}",
                ]
                result = subprocess.run(
                    cmd_fallback,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    print(f"    Fallback also failed: {result.stderr[:500]}")
                    continue

            size = pdf_path.stat().st_size
            print(f"    -> {pdf_path.name} ({size:,} bytes)")
            generated += 1

        except subprocess.TimeoutExpired:
            print(f"    pandoc timed out for {md_name}")
        except FileNotFoundError:
            print("    pandoc not found. Install: brew install pandoc")
            break

    print(f"\n  Generated {generated} PDFs.")
