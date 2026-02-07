"""Step 7: Generate moot court Q&A using Claude CLI."""

from pathlib import Path

from ..config import ProjectConfig
from ..prompts.moot_qa import build_prompt
from ..utils.claude_runner import run_claude
from ..utils.file_utils import find_brief_texts


def run(config: ProjectConfig):
    """Generate MOOT_QA.md from all briefs, issue analysis, and cite-check."""
    output_path = config.project_dir / "MOOT_QA.md"

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"  Skipping (already exists): {output_path.name}")
        return

    # Read briefs
    txt_files = find_brief_texts(config.project_dir)
    if not txt_files:
        raise FileNotFoundError("No .txt files found. Run the 'convert' step first.")

    brief_texts = {}
    for f in txt_files:
        brief_texts[f.name] = f.read_text(errors="replace")

    # Read issue analysis
    analysis_path = config.project_dir / "ISSUE_ANALYSIS.md"
    if not analysis_path.exists():
        raise FileNotFoundError("ISSUE_ANALYSIS.md not found. Run the 'analysis' step first.")
    issue_analysis_text = analysis_path.read_text()

    # Read cite-check
    citecheck_path = config.project_dir / "CITECHECK.md"
    if not citecheck_path.exists():
        raise FileNotFoundError("CITECHECK.md not found. Run the 'citecheck' step first.")
    citecheck_text = citecheck_path.read_text()

    print(f"  Generating moot court Q&A from {len(brief_texts)} briefs...")
    prompt = build_prompt(brief_texts, issue_analysis_text, citecheck_text)

    result = run_claude(
        prompt=prompt,
        model=config.claude_model,
    )

    output_path.write_text(result)
    print(f"  Written: {output_path.name} ({output_path.stat().st_size:,} bytes)")
