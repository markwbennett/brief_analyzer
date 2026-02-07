"""Step 7: Generate moot court Q&A using Claude CLI."""

from pathlib import Path

from ..config import ProjectConfig
from ..prompts.moot_qa import build_prompt, build_tool_prompt
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

    # Check prerequisites
    analysis_path = config.project_dir / "ISSUE_ANALYSIS.md"
    if not analysis_path.exists():
        raise FileNotFoundError("ISSUE_ANALYSIS.md not found. Run the 'analysis' step first.")

    citecheck_path = config.project_dir / "CITECHECK.md"
    if not citecheck_path.exists():
        raise FileNotFoundError("CITECHECK.md not found. Run the 'citecheck' step first.")

    # Use tool-based prompt to avoid exceeding context limits
    brief_paths = [str(f) for f in txt_files]
    print(f"  Generating moot court Q&A from {len(brief_paths)} briefs...")
    prompt = build_tool_prompt(
        brief_paths, str(analysis_path), str(citecheck_path), str(config.authorities_dir)
    )

    result = run_claude(
        prompt=prompt,
        model=config.claude_model,
        add_dirs=[config.project_dir, config.authorities_dir],
    )

    output_path.write_text(result)
    print(f"  Written: {output_path.name} ({output_path.stat().st_size:,} bytes)")
