"""Command-line interface for the brief analyzer."""

import argparse
from pathlib import Path
from typing import Optional

from .config import ProjectConfig, load_config
from .state import STEP_NAMES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brief_analyzer",
        description="Appellate Brief Analyzer -- automated pipeline for Texas appellate brief analysis.",
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to the project directory (where briefs live or will be downloaded)",
    )
    parser.add_argument(
        "--case",
        dest="case_number",
        help="Case number to fetch from txcourts.gov (e.g., 01-24-00686-CR)",
    )
    parser.add_argument(
        "--coa",
        help="Court of appeals code (e.g., coa01). Default: inferred from case number.",
    )
    parser.add_argument(
        "--step",
        choices=STEP_NAMES,
        help="Run a single pipeline step",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the first incomplete step",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Number of parallel Claude agents for cite-check (default: 4)",
    )
    parser.add_argument(
        "--model",
        default="opus",
        help="Claude model to use (default: opus)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to brief_config.yaml",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show pipeline status and exit",
    )
    return parser


def parse_args(argv: Optional[list[str]] = None) -> tuple[ProjectConfig, argparse.Namespace]:
    """Parse CLI args and return (config, args)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(
        config_path=args.config,
        project_dir=args.project_dir,
        case_number=args.case_number,
        coa=args.coa,
        model=args.model,
        parallel=args.parallel,
    )

    return config, args
