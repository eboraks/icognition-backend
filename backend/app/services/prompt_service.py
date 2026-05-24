"""
YAML-backed prompt and skill loader.

Replaces the former DB-backed PromptService.  All prompts and skills are now
read from ``backend/agent/prompts/*.yaml`` at first access and cached in memory
for the lifetime of the process.
"""

import numpy as np
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
_skill_embeddings: Dict[str, List[float]] = {}  # skill_key → embedding vector


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
                node_name=s.get("node_name", "generate_node"),
                description=s.get("description", ""),
                slash_instruction=s.get("slash_instruction", ""),
                prompt_text=s.get("prompt_text"),
                # Reflection is opt-in per skill. When True, generate_node
                # routes through reflect_node; when False, the first draft
                # is returned as-is.
                reflect=bool(s.get("reflect", False)),
                # When True, this skill short-circuits into the research
                # multi-agent sub-graph instead of generate_node. Only the
                # "research" skill should set this.
                research=bool(s.get("research", False)),
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
# Embedding-based skill matching
# ---------------------------------------------------------------------------

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    a = np.array(vec1)
    b = np.array(vec2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def _compute_skill_embeddings() -> None:
    """Pre-compute and cache embeddings for all skill descriptions."""
    from app.services.embedding_service import get_embedding_service

    _load_all()
    svc = get_embedding_service()

    for key, skill in _skills.items():
        text = f"{skill.description}. {skill.slash_instruction}"
        result = await svc.generate_embedding(
            text=text,
            task_type="SEMANTIC_SIMILARITY",
        )
        if result.success:
            _skill_embeddings[key] = result.embedding
            logger.debug(f"Cached embedding for skill '{key}'")
        else:
            logger.warning(f"Failed to compute embedding for skill '{key}': {result.error}")

    logger.info(f"Computed embeddings for {len(_skill_embeddings)}/{len(_skills)} skills")


async def match_skill(user_message: str, threshold: float = 0.5) -> str:
    """
    Find the best matching skill for a user message via embedding similarity.

    Returns the skill key with the highest cosine similarity above *threshold*,
    or the default skill if no match is found.
    """
    if not _skill_embeddings:
        await _compute_skill_embeddings()

    from app.services.embedding_service import get_embedding_service

    svc = get_embedding_service()
    msg_result = await svc.generate_embedding(
        text=user_message,
        task_type="SEMANTIC_SIMILARITY",
    )
    if not msg_result.success:
        logger.warning(f"Failed to embed user message for skill matching: {msg_result.error}")
        return get_default_skill()

    best_skill = get_default_skill()
    best_score = threshold

    for key, skill_vec in _skill_embeddings.items():
        score = _cosine_similarity(msg_result.embedding, skill_vec)
        if score > best_score:
            best_score = score
            best_skill = key

    logger.info(f"Skill match: '{best_skill}' (score={best_score:.3f}) for message: '{user_message[:80]}...'")
    return best_skill


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
