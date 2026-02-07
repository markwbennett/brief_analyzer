"""Pipeline state persistence -- tracks step completion for resumability."""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Canonical step names in execution order
STEP_NAMES = [
    "fetch",
    "convert",
    "authorities",
    "courtlistener",
    "westlaw",
    "process",
    "verify",
    "citecheck",
    "analysis",
    "mootqa",
    "pdf",
]

STEP_DESCRIPTIONS = {
    "fetch": "Download filings from txcourts.gov",
    "convert": "Convert PDFs to text",
    "authorities": "Extract authorities list",
    "courtlistener": "Download cases from CourtListener (free)",
    "westlaw": "Download remaining cases from Westlaw",
    "process": "Process and rename authority files",
    "verify": "Verify all authorities are downloaded",
    "citecheck": "Cite-check all briefs",
    "analysis": "Generate issue analysis",
    "mootqa": "Generate moot court Q&A",
    "pdf": "Generate PDF outputs",
}


@dataclass
class StepState:
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None


@dataclass
class PipelineState:
    steps: dict[str, StepState] = field(default_factory=dict)

    def __post_init__(self):
        for name in STEP_NAMES:
            if name not in self.steps:
                self.steps[name] = StepState()

    def save(self, path: Path):
        data = {}
        for name, step in self.steps.items():
            data[name] = {"status": step.status.value, "error": step.error}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        state = cls()
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            for name, info in data.items():
                if name in state.steps:
                    state.steps[name] = StepState(
                        status=StepStatus(info["status"]),
                        error=info.get("error"),
                    )
        return state

    def mark(self, step: str, status: StepStatus, error: Optional[str] = None):
        self.steps[step].status = status
        self.steps[step].error = error

    def first_incomplete(self) -> Optional[str]:
        """Return the first step that hasn't completed."""
        for name in STEP_NAMES:
            if self.steps[name].status not in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                return name
        return None

    def summary(self) -> str:
        lines = []
        for name in STEP_NAMES:
            step = self.steps[name]
            icon = {
                StepStatus.PENDING: " ",
                StepStatus.RUNNING: ">",
                StepStatus.COMPLETED: "x",
                StepStatus.FAILED: "!",
                StepStatus.SKIPPED: "-",
            }[step.status]
            desc = STEP_DESCRIPTIONS.get(name, name)
            line = f"[{icon}] {name}: {desc}"
            if step.error:
                line += f" (error: {step.error})"
            lines.append(line)
        return "\n".join(lines)
