"""Pipeline orchestrator -- runs steps in sequence, manages state."""

import sys
from typing import Optional

from .config import ProjectConfig
from .state import PipelineState, StepStatus, STEP_NAMES
from .steps.s0_fetch_case import run as fetch_case
from .steps.s1_convert_pdfs import run as convert_pdfs
from .steps.s2_extract_authorities import run as extract_authorities
from .steps.s2b_courtlistener import run as courtlistener_download
from .steps.s3_westlaw_download import run as westlaw_download
from .steps.s4_process_authorities import run as process_authorities
from .steps.s5_verify_authorities import run as verify_authorities
from .steps.s5_citecheck import run as citecheck
from .steps.s6_issue_analysis import run as issue_analysis
from .steps.s7_moot_qa import run as moot_qa
from .steps.s8_generate_pdfs import run as generate_pdfs

STEP_RUNNERS = {
    "fetch": fetch_case,
    "convert": convert_pdfs,
    "authorities": extract_authorities,
    "courtlistener": courtlistener_download,
    "westlaw": westlaw_download,
    "rtf2text": process_authorities,
    "verify": verify_authorities,
    "citecheck": citecheck,
    "analysis": issue_analysis,
    "mootqa": moot_qa,
    "pdf": generate_pdfs,
}


def run_pipeline(
    config: ProjectConfig,
    single_step: Optional[str] = None,
    resume: bool = False,
):
    """Run the full pipeline or a single step."""
    config.ensure_dirs()
    state = PipelineState.load(config.state_file)

    if single_step:
        steps_to_run = [single_step]
    elif resume:
        first = state.first_incomplete()
        if first is None:
            print("All steps already completed.")
            return
        idx = STEP_NAMES.index(first)
        steps_to_run = STEP_NAMES[idx:]
        print(f"Resuming from step: {first}")
    else:
        steps_to_run = list(STEP_NAMES)

    # Skip fetch step if no case number provided
    if "fetch" in steps_to_run and not config.case_number:
        print("No --case provided, skipping fetch step.")
        state.mark("fetch", StepStatus.SKIPPED)
        state.save(config.state_file)
        steps_to_run.remove("fetch")

    for step_name in steps_to_run:
        runner = STEP_RUNNERS[step_name]
        print(f"\n{'='*60}")
        print(f"Step: {step_name}")
        print(f"{'='*60}")

        state.mark(step_name, StepStatus.RUNNING)
        state.save(config.state_file)

        try:
            runner(config)
            state.mark(step_name, StepStatus.COMPLETED)
            state.save(config.state_file)
            print(f"Step {step_name}: completed.")
        except KeyboardInterrupt:
            state.mark(step_name, StepStatus.FAILED, error="Interrupted by user")
            state.save(config.state_file)
            print(f"\nStep {step_name}: interrupted. Use --resume to continue.")
            sys.exit(1)
        except Exception as e:
            state.mark(step_name, StepStatus.FAILED, error=str(e))
            state.save(config.state_file)
            print(f"Step {step_name}: FAILED -- {e}")
            print("Use --resume to retry from this step.")
            raise
