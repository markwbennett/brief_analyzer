"""Step 2: Extract authorities from briefs using Claude CLI."""

from pathlib import Path

from ..config import ProjectConfig
from ..prompts.authority_extraction import build_prompt
from ..utils.claude_runner import run_claude
from ..utils.file_utils import find_all_texts


def run(config: ProjectConfig):
    """Extract authorities from all brief texts and produce AUTHORITIES.md."""
    output_path = config.project_dir / "AUTHORITIES.md"

    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"  Skipping (already exists): {output_path.name}")
        return

    # Read all brief texts
    txt_files = find_all_texts(config.project_dir)
    if not txt_files:
        raise FileNotFoundError("No .txt files found. Run the 'convert' step first.")

    brief_texts = {}
    for f in txt_files:
        brief_texts[f.name] = f.read_text(errors="replace")

    print(f"  Analyzing {len(brief_texts)} text files...")
    prompt = build_prompt(brief_texts)

    result = run_claude(
        prompt=prompt,
        model=config.claude_model,
        add_dirs=[config.authorities_dir],
    )

    output_path.write_text(result)
    print(f"  Written: {output_path.name} ({output_path.stat().st_size:,} bytes)")
