# Chat Agent: Skills, Prompts & Nodes Architecture

## Overview

The chat agent uses a LangGraph `StateGraph` (`research_graph.py`) where user messages flow through a pipeline of nodes. A **skill** determines which system prompt and generation behavior to apply.

## Architecture Diagram

```
START
  │
  ▼
┌─────────────┐
│ intent_node  │  ← Classifies user intent → skill: str
└─────┬───────┘
      │
      ▼
┌──────────────┐
│ enrich_kg    │  ← Resolves entities against Knowledge Graph
└─────┬────────┘
      │
      ▼
┌─────────────────────┐
│ route_by_skill()    │  ← Conditional edge based on state["skill"]
└──┬──┬──┬──┬──┬──────┘
   │  │  │  │  │
   ▼  ▼  ▼  ▼  ▼
  qa social email summary ... (skill_generate_node)
   │  │  │  │  │
   └──┴──┴──┴──┘
      │
      ▼
┌─────────────────────┐
│ route_after_generate │  ← tool_calls? → tools node (loop back)
└─────┬───────────────┘   └──── no ────→ reflect_node
      │
      ▼
┌──────────────┐
│ reflect_node │  ← Critiques answer quality
└─────┬────────┘
      │
      ▼
┌──────────────────────┐
│ route_after_reflect  │
│  - satisfactory → END│
│  - needs_search → google_search_node → re-generate
│  - retry → re-generate (via skill router)
└──────────────────────┘
```

## Skill Registry

Defined in `research_graph.py` as `SKILL_REGISTRY`:

| Skill Key      | PromptType                      | Description                        | Fallback |
|----------------|---------------------------------|------------------------------------|----------|
| `qa`           | `CHAT_AGENT_SYSTEM`             | Default knowledge Q&A              | Required (raises if missing) |
| `social_post`  | `CHAT_SOCIAL_WRITER`            | Social media comment drafts        | Hardcoded `_SOCIAL_WRITER_FALLBACK` |
| `email_draft`  | `CHAT_SKILL_EMAIL_DRAFT`        | Email drafting                     | Hardcoded fallback |
| `summary`      | `CHAT_SKILL_SUMMARY`            | Document/topic summarization       | Hardcoded fallback |
| `fact_check`   | `CHAT_SKILL_FACT_CHECK`         | Fact checking & claim verification | Hardcoded fallback |

### Registry Structure

```python
SKILL_REGISTRY: Dict[str, SkillConfig] = {
    "qa": SkillConfig(
        prompt_type=PromptType.CHAT_AGENT_SYSTEM,
        node_name="generate_node",
        description="Knowledge Q&A",
        fallback_prompt=None,  # required in DB
    ),
    "social_post": SkillConfig(
        prompt_type=PromptType.CHAT_SOCIAL_WRITER,
        node_name="social_generate_node",
        description="Social media writing",
        fallback_prompt=_SOCIAL_WRITER_FALLBACK,
    ),
    ...
}
```

## How Skills, Prompts, and Nodes Connect

### 1. Intent Classification (`intent_node`)

- Uses `PromptType.CHAT_INTENT_CLASSIFICATION` prompt from DB
- LLM returns `IntentClassification` structured output with `skill: str`
- The `skill` value must match a key in `SKILL_REGISTRY`
- Falls back to `"qa"` if the returned skill is not in the registry

### 2. Skill Routing (`route_by_skill`)

- Reads `state["skill"]` set by `intent_node`
- Returns the `node_name` from the matching `SkillConfig`
- All skill generate nodes share the same `_run_generate()` logic
- The only difference is which system prompt is injected

### 3. Prompt Resolution (per skill)

Each skill's generate node:
1. Looks up `SkillConfig.prompt_type` in the pre-fetched `prompts` dict
2. If found → uses `system_prompt` + `user_prompt` from DB
3. If not found → uses `SkillConfig.fallback_prompt` (or raises if `None`)

### 4. Tools

All skills share the same tool set:
- `retrieve_documents_tool` — KB vector search
- `fetch_social_post_tool` — Fetch URL content
- `world_context_tool` — Current events via Google Search
- `google_search_tool` — Web search
- `kg_tool` — Knowledge Graph search

After tool execution, the graph loops back to the same skill's generate node.

### 5. Reflection (`reflect_node`)

- Uses `PromptType.CHAT_REFLECTION` prompt
- Shared across all skills — critiques the response regardless of skill
- Can trigger: END, google_search, or retry (routes back via `route_by_skill`)

## Adding a New Skill

1. **Add PromptType** in `prompt_utils.py`:
   ```python
   CHAT_SKILL_MY_SKILL = "Chat Skill: My Skill"
   ```

2. **Add to SKILL_REGISTRY** in `research_graph.py`:
   ```python
   "my_skill": SkillConfig(
       prompt_type=PromptType.CHAT_SKILL_MY_SKILL,
       node_name="my_skill_generate_node",
       description="Description of what this skill does",
       fallback_prompt="Fallback system prompt if DB prompt missing...",
   ),
   ```

3. **Add prompt to DB** via admin UI (`/admin/prompts`):
   - Type: `Chat Skill: My Skill`
   - System prompt: The system instructions for this skill
   - User prompt: Optional template

4. **Update intent classification prompt** in DB to include the new skill name in the list of possible skill values.

5. **Add slash command** in `ChatPanel.vue` and `ChatInterface.vue` `SKILL_SHORTCUTS` map:
   ```javascript
   '/my_skill': 'my_skill',
   ```

6. **Optionally add a quick action button** in the `quick-actions-row` template section.

## Slash Commands & Skill Override

Users can force a skill via:
- **Slash commands** in the chat input: `/fact_check`, `/social_post`, `/summary`, `/email`, `/summarize`, `/write_comment`
- **Quick action buttons** above the input field

The slash command is intercepted in the frontend before sending. The `skill` parameter is passed as a query param on the SSE stream URL (`?skill=fact_check`), which flows through:
1. `chat.py` SSE endpoint → `skill` query param
2. `ChatAgentService.get_stream()` → `skill_override` kwarg
3. `build_research_graph()` → `skill_override` param
4. `intent_node` → skips LLM classification, uses override directly

| Command | Skill Key | Description |
|---------|-----------|-------------|
| `/social_post`, `/write_comment` | `social_post` | Write social media comments |
| `/fact_check` | `fact_check` | Fact check claims |
| `/summary`, `/summarize` | `summary` | Summarize documents |
| `/email`, `/email_draft` | `email_draft` | Draft emails |

## File References

| File | Role |
|------|------|
| `backend/app/chat_workflows/research_graph.py` | Graph definition, skill registry, all nodes |
| `backend/app/services/prompt_utils.py` | `PromptType` enum |
| `backend/app/services/prompt_service.py` | DB prompt fetching with TTL cache |
| `backend/app/services/chat_agent_service.py` | Orchestrator: builds graph, manages sessions |
| `backend/app/chat_workflows/tools.py` | Tool definitions |
