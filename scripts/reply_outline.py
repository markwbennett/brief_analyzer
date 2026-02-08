#!/usr/bin/env python3
"""Generate a reply-brief argument outline from the opening brief, State's brief, and authorities.

Usage:
    python scripts/reply_outline.py <project_dir>

Outputs REPLY_OUTLINE.md and REPLY_OUTLINE.pdf in the project directory.
"""

import os
import subprocess
import sys
from pathlib import Path


def find_briefs(project_dir: Path) -> tuple[Path, Path]:
    """Find the appellant's opening brief and the State's response brief."""
    opening = None
    state = None

    for f in sorted(project_dir.glob("*.txt")):
        name_lower = f.name.lower()
        # Skip small files (procedural filings)
        if f.stat().st_size < 10_000:
            continue
        if "reply" in name_lower:
            continue
        if "appellant" in name_lower or "opening" in name_lower:
            opening = f
        elif "state" in name_lower and ("brief" in name_lower or "filed" in name_lower):
            state = f

    if not opening:
        raise FileNotFoundError("No appellant/opening brief found in project directory")
    if not state:
        raise FileNotFoundError("No State's response brief found in project directory")

    return opening, state


def build_prompt(opening_path: Path, state_path: Path, authorities_dir: Path) -> str:
    """Build the reply-outline prompt for Claude."""

    # List all authority files so Claude knows what's available
    auth_files = sorted(f.name for f in authorities_dir.glob("*.txt")
                        if not f.name.startswith("."))
    auth_listing = "\n".join(f"- {authorities_dir}/{name}" for name in auth_files)

    return f"""You are a senior Texas criminal-defense appellate attorney. Your client lost at trial and has filed an opening brief. The State has filed its response. You must now outline the argument for a reply brief.

## Files

Read each of these files using the Read tool:

**Appellant's Opening Brief:**
- {opening_path}

**State's Response Brief:**
- {state_path}

**Authorities available** (read as needed to verify holdings, find quotable language, and check what the cases actually say):
{auth_listing}

Read both briefs in full before beginning. Then read authorities as needed.

## What a Reply Brief Is

A reply brief is NOT a second opening brief. It responds to the State's response. Its job is to:

1. Identify what the State actually argues (not what you wish it argued)
2. Show where the State's arguments fail---by distinguishing its authorities, exposing mischaracterizations, and demonstrating that its reasoning does not follow
3. Reinforce the opening brief's strongest points where the State's response is weakest
4. Concede nothing implicitly---if the State makes an argument, the reply must address it or the court may treat it as conceded

## Instructions

Produce a detailed reply-brief argument outline. For each issue in the case:

### A. State the Issue
Frame the issue as the court would see it.

### B. What the State Argues
Summarize every distinct argument the State makes on this issue. Do not skip arguments that seem weak---weak arguments still need responses. Quote the State's brief where its language matters. Identify which authorities the State relies on and what it claims they stand for.

### C. Reply Strategy
For each of the State's arguments, provide:

1. **The response**: What the reply brief should say. Be specific---not "distinguish Herzbrun" but "Herzbrun is an airport-security case (723 F.2d at 775: 'airport security checkpoints and loading gates are sui generis under the fourth amendment'). The airport exception exists because a departing passenger who abandons screening may still board through another gate; a jail visitor who leaves eliminates the security risk entirely."

2. **The authority**: Which case(s) support the response, with specific holdings and pin cites from the actual opinion text (read the authority files). Quote the best language from each authority. Do not cite a case for a proposition unless you have read the authority file and confirmed it holds what you say it holds.

3. **The structure**: How this argument fits into the larger reply. Does it stand alone, or does it set up the next point?

### D. Affirmative Points to Make
Identify arguments the reply brief should make affirmatively (not just in response to the State), such as:
- Points the State concedes or fails to address
- Authorities the State ignores that are directly on point
- Logical consequences of the State's own position that the State does not acknowledge

### E. What to Avoid
Note any arguments from the existing reply-brief draft (if you are aware of one) or common mistakes that would weaken the brief:
- Overstating holdings
- Citing cases for propositions they do not support
- Using inflammatory language where precision would be more persuasive
- Repeating the opening brief's arguments verbatim instead of advancing them

## Format

Use markdown. Organize by issue. Under each issue, use the A-E structure above. Include full citations with pin cites for every authority you reference. When you quote from an authority, give the exact page.

## Standards

- Every factual claim about what a case holds must be verified against the authority text file. If you have not read the file, do not cite the case.
- Prefer precise, quotable language from opinions over paraphrase.
- Identify the 2-3 arguments most likely to be decisive and mark them.
- Note where the State's position creates openings that the reply can exploit.
- If the State cites a case that actually helps the appellant, say so and explain why.
- Do not sugarcoat. If an argument is weak, say it is weak and explain why. If an issue is likely to be lost, say so and focus the outline on the issues that can be won.

Output the full REPLY_OUTLINE.md content. Do not use the Write tool. Print it directly to stdout."""


def run_claude(prompt: str, add_dirs: list[Path]) -> str:
    """Run claude --print with tool access."""
    cmd = [
        "claude",
        "--print",
        "--model", "opus",
        "--allowedTools", "Read,Bash(ls:*)",
    ]
    for d in add_dirs:
        cmd.extend(["--add-dir", str(d)])

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    print("Running Claude (opus, with tool access)...")
    print(f"  Command: {' '.join(cmd[:6])}...")

    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        print(f"Claude CLI failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr[:1000], file=sys.stderr)
        sys.exit(1)

    return result.stdout.strip()


def generate_pdf(md_path: Path):
    """Convert markdown to PDF using pandoc + xelatex."""
    pdf_path = md_path.with_suffix(".pdf")

    cmd = [
        "pandoc",
        str(md_path),
        "-o", str(pdf_path),
        "--pdf-engine=xelatex",
        "-V", "mainfont=Equity B",
        "-V", "sansfont=Concourse 6",
        "-V", "fontsize=14pt",
        "-V", "geometry:margin=1.5in",
        "-V", "documentclass=extarticle",
        "--include-in-header=/dev/stdin",
    ]

    latex_header = (
        r"\usepackage{titlesec}" "\n"
        r"\titleformat{\section}{\Large\sffamily\bfseries}{\thesection}{1em}{}" "\n"
        r"\titleformat{\subsection}{\large\sffamily\bfseries}{\thesubsection}{1em}{}" "\n"
        r"\titleformat{\subsubsection}{\normalsize\sffamily\bfseries}{\thesubsubsection}{1em}{}" "\n"
    )

    try:
        result = subprocess.run(
            cmd, input=latex_header, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  pandoc failed: {result.stderr[:500]}")
            print("  Retrying with Courier fallback...")
            cmd_fallback = [
                "pandoc", str(md_path), "-o", str(pdf_path),
                "--pdf-engine=xelatex",
                "-V", "mainfont=Courier",
                "-V", "fontsize=14pt",
                "-V", "geometry:margin=1.5in",
                "-V", "documentclass=extarticle",
            ]
            result = subprocess.run(
                cmd_fallback, capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                print(f"  Fallback also failed: {result.stderr[:500]}")
                return

        print(f"  -> {pdf_path.name} ({pdf_path.stat().st_size:,} bytes)")
    except subprocess.TimeoutExpired:
        print("  pandoc timed out")
    except FileNotFoundError:
        print("  pandoc not found. Install: brew install pandoc")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <project_dir>")
        sys.exit(1)

    project_dir = Path(sys.argv[1]).resolve()
    authorities_dir = project_dir / "authorities"

    if not authorities_dir.exists():
        print(f"No authorities/ directory in {project_dir}")
        sys.exit(1)

    opening, state = find_briefs(project_dir)
    print(f"Opening brief: {opening.name} ({opening.stat().st_size:,} bytes)")
    print(f"State's brief: {state.name} ({state.stat().st_size:,} bytes)")

    n_auth = len(list(authorities_dir.glob("*.txt")))
    print(f"Authorities: {n_auth} files in {authorities_dir}")

    prompt = build_prompt(opening, state, authorities_dir)
    result = run_claude(prompt, add_dirs=[project_dir, authorities_dir])

    output_md = project_dir / "REPLY_OUTLINE.md"
    output_md.write_text(result)
    print(f"\nWritten: {output_md.name} ({output_md.stat().st_size:,} bytes)")

    print("Generating PDF...")
    generate_pdf(output_md)


if __name__ == "__main__":
    main()
