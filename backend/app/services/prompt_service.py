"""
YAML-backed prompt and skill loader.

Replaces the former DB-backed PromptService.  All prompts and skills are now
read from ``backend/agent/prompts/*.yaml`` at first access and cached in memory
for the lifetime of the process.
"""

import yaml
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Path to the agent YAML directory
# ---------------------------------------------------------------------------
_AGENT_DIR = Path(__file__).resolve().parent.parent.parent / "agent"

# ---------------------------------------------------------------------------
# Module-level caches populated once at first access
# ---------------------------------------------------------------------------
_prompts: Dict[str, SimpleNamespace] = {}
_skills: Dict[str, SimpleNamespace] = {}
_default_skill: str = "qa"
_loaded: bool = False


# ---------------------------------------------------------------------------
# Internal loader
# ---------------------------------------------------------------------------

def _load_all() -> None:
    """Read every ``*.yaml`` in ``agent/prompts/`` and populate caches."""
    global _loaded, _default_skill
    if _loaded:
        return

    prompts_dir = _AGENT_DIR / "prompts"
    if not prompts_dir.exists():
        logger.error(f"Prompts directory not found: {prompts_dir}")
        _loaded = True
        return

    # --- Load prompt files ---------------------------------------------------
    for yaml_file in sorted(prompts_dir.glob("*.yaml")):
        if yaml_file.name == "skills.yaml":
            continue  # handled separately below
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        if not data:
            continue
        for p in data.get("prompts", []):
            pt = p["prompt_type"]
            _prompts[pt] = SimpleNamespace(
                prompt_type=pt,
                system_prompt=p.get("system_prompt"),
                user_prompt=p.get("user_prompt", ""),
                description=p.get("description"),
            )

    # --- Load skills ---------------------------------------------------------
    skills_file = prompts_dir / "skills.yaml"
    if skills_file.exists():
        with open(skills_file) as f:
            skills_data = yaml.safe_load(f) or {}
        _default_skill = skills_data.get("default_skill", "qa")
        for s in skills_data.get("skills", []):
            key = s["key"]
            _skills[key] = SimpleNamespace(
                key=key,
                prompt_type=s["prompt_type"],
                node_name=s["node_name"],
                description=s.get("description", ""),
                slash_instruction=s.get("slash_instruction", ""),
                prompt_text=s.get("prompt_text"),
            )

    _loaded = True
    logger.info(
        f"Loaded {len(_prompts)} prompts and {len(_skills)} skills from "
        f"{prompts_dir}"
    )


# ---------------------------------------------------------------------------
# Public API — prompts
# ---------------------------------------------------------------------------

def get_prompt(prompt_type: str) -> Optional[SimpleNamespace]:
    """
    Return the prompt for *prompt_type*, or ``None`` if not found.

    The returned ``SimpleNamespace`` has ``.system_prompt``, ``.user_prompt``,
    and ``.description`` — the same interface the old DB-backed
    ``PromptService.get_latest_prompt()`` returned.
    """
    _load_all()
    return _prompts.get(prompt_type)


def get_all_prompts() -> Dict[str, SimpleNamespace]:
    """Return a copy of the full prompt dict (keyed by prompt_type)."""
    _load_all()
    return dict(_prompts)


# ---------------------------------------------------------------------------
# Public API — skills
# ---------------------------------------------------------------------------

def get_skill(skill_key: str) -> Optional[SimpleNamespace]:
    """Return the skill config for *skill_key*, or ``None``."""
    _load_all()
    return _skills.get(skill_key)


def get_all_skills() -> Dict[str, SimpleNamespace]:
    """Return a copy of the full skill dict (keyed by skill key)."""
    _load_all()
    return dict(_skills)


def get_default_skill() -> str:
    """Return the default skill key (e.g. ``"qa"``)."""
    _load_all()
    return _default_skill


# ---------------------------------------------------------------------------
# Backward-compatible wrapper
# ---------------------------------------------------------------------------

class PromptService:
    """
    Thin compatibility shim so existing callers that do
    ``PromptService(session).get_latest_prompt(pt)`` keep working without
    modification.  The *session* argument is accepted but ignored.
    """

    def __init__(self, session=None):
        pass  # session no longer needed

    async def get_latest_prompt(self, prompt_type: str) -> Optional[SimpleNamespace]:
        return get_prompt(prompt_type)
