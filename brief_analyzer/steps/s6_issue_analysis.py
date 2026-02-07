"""Step 6: Generate issue analysis using Claude CLI."""

from pathlib import Path

from ..config import ProjectConfig
from ..prompts.issue_analysis import build_prompt, build_tool_prompt
from ..utils.claude_runner import run_claude
from ..utils.file_utils import find_brief_texts


def run(config: ProjectConfig):
    """Generate ISSUE_ANALYSIS.md from all briefs and cite-check results."""
    output_path = config.project_dir / "ISSUE_ANALYSIS.md"

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"  Skipping (already exists): {output_path.name}")
        return

    # Read briefs
    txt_files = find_brief_texts(config.project_dir)
    if not txt_files:
        raise FileNotFoundError("No .txt files found. Run the 'convert' step first.")

    # Read cite-check
    citecheck_path = config.project_dir / "CITECHECK.md"
    if not citecheck_path.exists():
        raise FileNotFoundError("CITECHECK.md not found. Run the 'citecheck' step first.")

    # Use tool-based prompt: tell Claude to read files itself rather than
    # embedding 300K+ chars in the prompt (which exceeds context limits).
    brief_paths = [str(f) for f in txt_files]
    print(f"  Analyzing {len(brief_paths)} briefs with cite-check results...")
    prompt = build_tool_prompt(brief_paths, str(citecheck_path), str(config.authorities_dir))

    result = run_claude(
        prompt=prompt,
        model=config.claude_model,
        add_dirs=[config.project_dir, config.authorities_dir],
    )

    output_path.write_text(result)
    print(f"  Written: {output_path.name} ({output_path.stat().st_size:,} bytes)")
