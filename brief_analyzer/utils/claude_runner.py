"""Subprocess wrapper for invoking claude --print."""

import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_claude(
    prompt: str,
    model: str = "opus",
    add_dirs: Optional[list[Path]] = None,
    allowed_tools: str = "Read,Bash(ls:*)",
    timeout: Optional[int] = None,
) -> str:
    """Run claude --print with the given prompt via stdin.

    Returns the model's text output.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    cmd = [
        "claude",
        "--print",
        "--model", model,
        "--allowedTools", allowed_tools,
    ]
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", str(d)])

    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        print(f"Claude CLI stderr: {result.stderr}", file=sys.stderr)
        result.check_returncode()

    return result.stdout.strip()
