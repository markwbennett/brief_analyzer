"""Project configuration via dataclass + YAML loading."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CourtListenerConfig:
    api_token: str = ""


@dataclass
class WestlawConfig:
    username: str = ""
    password: str = ""
    client_matter: str = ""
    login_url: str = "https://next.westlaw.com"


@dataclass
class PandocConfig:
    font: str = "Equity B"
    font_size: int = 14
    heading_font: str = "Concourse 6"
    margins: str = "1.5in"
    document_class: str = "extarticle"


@dataclass
class ProjectConfig:
    project_dir: Path = field(default_factory=lambda: Path.cwd())
    case_number: Optional[str] = None
    coa: Optional[str] = None
    courtlistener: CourtListenerConfig = field(default_factory=CourtListenerConfig)
    westlaw: WestlawConfig = field(default_factory=WestlawConfig)
    pandoc: PandocConfig = field(default_factory=PandocConfig)
    claude_model: str = "opus"
    extraction_model: str = "haiku"
    verification_model: str = "opus"
    parallel_agents: int = 4

    @property
    def authorities_dir(self) -> Path:
        return self.project_dir / "authorities"

    @property
    def rtf_dir(self) -> Path:
        return self.authorities_dir / "rtf"

    @property
    def state_file(self) -> Path:
        return self.project_dir / ".pipeline_state.json"

    def infer_coa(self) -> str:
        """Infer court of appeals code from case number prefix."""
        if self.coa:
            return self.coa
        if self.case_number:
            prefix = self.case_number.split("-")[0]
            return f"coa{prefix}"
        raise ValueError("Cannot infer COA: no case number or --coa provided")

    def ensure_dirs(self):
        """Create project directories if they don't exist."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.authorities_dir.mkdir(exist_ok=True)
        self.rtf_dir.mkdir(exist_ok=True)


def load_config(config_path: Optional[Path] = None, **overrides) -> ProjectConfig:
    """Load config from YAML file, with CLI overrides applied on top."""
    data = {}
    if config_path and config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

    cl_data = data.pop("courtlistener", {}) or {}
    westlaw_data = data.pop("westlaw", {}) or {}
    pandoc_data = data.pop("pandoc", {}) or {}

    # CourtListener token: YAML > env var (check both naming conventions)
    cl_token = (
        cl_data.get("api_token", "")
        or os.environ.get("COURTLISTENER_TOKEN", "")
        or os.environ.get("COURT_LISTENER_TOKEN", "")
    )

    # Westlaw credentials: YAML > env var > Doppler
    wl_username = (
        westlaw_data.pop("username", "")
        or os.environ.get("WESTLAW_USERNAME", "")
    )
    wl_password = (
        westlaw_data.pop("password", "")
        or os.environ.get("WESTLAW_PASSWORD", "")
    )
    # Try Doppler if env vars are empty
    if not wl_username or not wl_password:
        try:
            import subprocess
            if not wl_username:
                wl_username = subprocess.run(
                    ["doppler", "secrets", "get", "WESTLAW_USERNAME", "--plain"],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
            if not wl_password:
                wl_password = subprocess.run(
                    ["doppler", "secrets", "get", "WESTLAW_PASSWORD", "--plain"],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    config = ProjectConfig(
        project_dir=Path(data.get("project_dir", overrides.get("project_dir", "."))),
        case_number=data.get("case_number", overrides.get("case_number")),
        coa=data.get("coa", overrides.get("coa")),
        courtlistener=CourtListenerConfig(api_token=cl_token),
        westlaw=WestlawConfig(
            username=wl_username,
            password=wl_password,
            **westlaw_data,
        ),
        pandoc=PandocConfig(**pandoc_data),
        claude_model=data.get("claude_model", overrides.get("model", "opus")),
        parallel_agents=data.get("parallel_agents", overrides.get("parallel", 4)),
    )

    # CLI overrides take precedence
    for key in ("case_number", "coa", "model", "parallel"):
        val = overrides.get(key)
        if val is not None:
            if key == "model":
                config.claude_model = val
            elif key == "parallel":
                config.parallel_agents = val
            else:
                setattr(config, key, val)

    return config
