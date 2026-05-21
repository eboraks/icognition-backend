# Agent Workflow

End-to-end reference for the iCognition chat agent: how a user message flows
from the SSE endpoint through the LangGraph state machine, which tools the
agent can call, how skills are selected, how reflection critiques drafts, how
the agent searches the user's library, and how it researches the open web.

If you only want the high-level skill/prompt/node mapping, see
[Map_Chat_Skill_Prompt_Nodes.md](../instructions/Map_Chat_Skill_Prompt_Nodes.md).
This document is the **implementation-level companion** — it cites the actual
code paths so a new contributor can trace every step.

---

## 1. High-level Architecture

```
                                ┌─────────────────────────┐
   POST /chat/stream ──────────►│ ChatAgentService.get_   │
   (SSE, with optional ?skill=) │ stream()                │
                                └──────────┬──────────────┘
                                           │  builds tools, loads prompts
                                           ▼
                                ┌─────────────────────────┐
                                │ build_research_graph()  │  ← Reflective Research Agent
                                │ (LangGraph StateGraph)  │
                                └──────────┬──────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                              ▼
        "normal" path (qa, social,                 requires_research=True
         summary, fact_check, …)                   ▼
                    │                  ┌──────────────────────────────┐
                    │                  │ build_research_multiagent_   │
                    │                  │ graph() — Plan + Execute     │
                    │                  │ + Supervisor (Tavily subagents)
                    │                  └──────────────────────────────┘
                    ▼
        SSE tokens streamed to client (tokens, status, draft_replace,
        chat_context, error)
```

Two graphs are involved:

1. **Reflective Research Agent** ([research_graph.py](../backend/app/chat_workflows/research_graph.py)) —
   the chat agent. Intent classification → skill routing → generation with
   tools → reflection loop. This is what serves every chat message.
2. **Research Multi-Agent** ([research_multiagent_graph.py](../backend/app/chat_workflows/research_multiagent_graph.py)) —
   a sub-graph dispatched only when the intent classifier sets
   `requires_research=True`. Plans sub-topics, runs Tavily-powered sub-agents
   in parallel, critiques coverage, writes a synthesized response with
   citations, and saves the source documents to the user's library.

Entry point: [chat_agent_service.py:258](../backend/app/services/chat_agent_service.py#L258)
(`ChatAgentService.get_stream`). It loads the chat session, builds
session-scoped tools, fetches prompts, retrieves the Postgres checkpointer,
compiles the graph, and streams events back as SSE.

---

## 2. The Reflective Research Agent (chat path)

### 2.1 Graph nodes

```
START
  │
  ▼
┌─────────────┐
│ intent_node │  ← classifies intent, picks skill,
└──────┬──────┘    flags requires_research
       │
       ▼
   ┌─────────────────────┐
   │ route_after_intent  │
   └───┬──────────────┬──┘
       │              │
       │ research?    │ otherwise
       ▼              ▼
┌─────────────────┐  ┌────────────────┐
│ dispatch_       │  │ generate_node  │ ◄──────────┐
│ research_node   │  │  (KG enrich +  │            │
│ (multi-agent)   │  │   LLM + tools) │            │
└──────┬──────────┘  └────────┬───────┘            │
       │                      │                    │
       ▼                      ▼                    │
      END         ┌──────────────────────┐         │
                  │ route_after_generate │         │
                  └────┬─────────────┬───┘         │
                       │             │             │
                       │ tool_calls? │ no          │
                       ▼             ▼             │
                  ┌────────┐    ┌─────────────┐    │
                  │ tools  │───►│ reflect_    │    │
                  │ (ToolNode)│ │ node        │    │
                  └────────┘    └──────┬──────┘    │
                                       │           │
                                       ▼           │
                              ┌────────────────┐   │
                              │ route_after_   │   │
                              │ reflect        │   │
                              └─┬───────────┬──┘   │
                                │           │      │
                                │ satisfied │ retry│
                                ▼           └──────┘
                               END
```

State definition: [research_graph.py:23](../backend/app/chat_workflows/research_graph.py#L23) (`AgentState`).
Key fields: `messages`, `skill`, `intent_description`, `latest_query`,
`extracted_entities`, `kg_context`, `context_entity_ids`,
`context_document_ids`, `is_satisfactory`, `reflection_count`,
`requires_research`.

### 2.2 intent_node — classification + skill selection

[research_graph.py:253](../backend/app/chat_workflows/research_graph.py#L253)

- Runs the prompt `Chat Agent: Intent Classification` with
  `with_structured_output(IntentClassification)`. Returns a `refined_query`,
  a `describe_the_user_message_intent` description, a `key_entities` list,
  and a `requires_research` boolean.
- Picks the **skill**:
  - If a `skill_override` was passed (slash command like `/fact_check`,
    `/summary`, `/email_draft`, `/write_social_media_post`,
    `/write_social_media_comment`), use it directly.
  - Otherwise call `match_skill(user_message)`
    ([prompt_service.py:174](../backend/app/services/prompt_service.py#L174)),
    which computes a Gemini embedding of the message and returns the skill
    whose `(description + slash_instruction)` embedding has the highest
    cosine similarity above `threshold=0.5`. Falls back to the
    `default_skill` from `skills.yaml` (currently `qa`).
- Per-turn state (`is_satisfactory`, `reflection_count`) is reset here so a
  prior turn's reflection state doesn't leak forward.

### 2.3 KG enrichment (inside generate_node)

[research_graph.py:310](../backend/app/chat_workflows/research_graph.py#L310)
(`_enrich_kg`) → [research_graph.py:54](../backend/app/chat_workflows/research_graph.py#L54)
(`resolve_entities_from_query`).

On the first generation pass per turn (`kg_context` is empty and
`extracted_entities` is non-empty), the graph fuzzy-matches each entity name
against the user's `kg_node` table using PostgreSQL `similarity()` (pg_trgm),
then pulls related `kg_edge` rows and the `document` rows the matched nodes
appear in. The result is formatted into a `[Knowledge Graph Context]` block
that gets injected into the user's last message before the LLM call.

This is **not** a tool — it runs deterministically on every generation pass
that has classified entities. The dedicated `knowledge_graph_tool` (below) is
how the LLM itself can pull KG data on demand.

### 2.4 generate_node — prompt resolution + LLM call

[research_graph.py:401](../backend/app/chat_workflows/research_graph.py#L401)
+ shared logic in `_run_generate`
[research_graph.py:329](../backend/app/chat_workflows/research_graph.py#L329).

1. Run KG enrichment (once per turn) → produces `kg_context` and
   `context_entity_ids`.
2. Resolve the skill's prompt:
   - Look up `SkillConfig.prompt_type` in the pre-fetched YAML prompts.
   - Fall back to the skill's inline `prompt_text` if no YAML entry exists.
   - Return an error message to the user if neither is configured.
3. Inject context into the last user message. Two paths:
   - **Slash command with no real content** (`/fact_check` alone) — replace
     the message with the skill's `slash_instruction` so the LLM has
     something concrete to act on.
   - **Normal turn** — append an `[Analysis Context]` block with the
     classified intent, refined query, and KG context.
4. Append a "tools reminder" listing every bound tool and instructing the
   LLM to call `retrieve_documents_tool` for library questions and
   `google_search_tool` for external questions.
5. Call `llm_with_tools.ainvoke(...)`. The LLM either returns text or
   `tool_calls`. Gemini's `MALFORMED_FUNCTION_CALL` is handled by a single
   retry without tools.

### 2.5 Tools loop

If `route_after_generate` sees `tool_calls`, the prebuilt LangGraph `ToolNode`
executes them, appends `ToolMessage` results, and edges back to `generate_node`.
The same skill prompt is used again — only the message history changes.

### 2.6 reflect_node — critique loop

[research_graph.py:438](../backend/app/chat_workflows/research_graph.py#L438).

- Skipped if the last AIMessage was a tool call (no draft yet to critique).
- Extracts only the **latest human/AI pair** from the history to avoid
  confusing the reflector with prior turns.
- Performs **role-swap**: the AI's answer is fed in as a `HumanMessage` and
  the user's question as an `AIMessage`. This frames the LLM as a teacher
  grading a student submission.
- Runs the prompt `Chat Agent: Reflection` with
  `with_structured_output(ReflectionOutput)` — returns
  `{critique, needs_search, search_query, is_satisfactory}`.
- If unsatisfied, the `critique` is appended as a `HumanMessage` so the next
  `generate_node` pass sees it and can revise.

`route_after_reflect` ([research_graph.py:726](../backend/app/chat_workflows/research_graph.py#L726))
ends the turn when `is_satisfactory=True` or `reflection_count > 3`,
otherwise sends the state back through `generate_node` (and the same skill
prompt).

### 2.7 Streaming protocol (SSE events)

[chat_agent_service.py:444](../backend/app/services/chat_agent_service.py#L444)
streams using `stream_mode=["messages", "values"]`. Events emitted to the
frontend:

| Event type        | When                                           |
|-------------------|------------------------------------------------|
| `status`          | intent classified, researching, refining       |
| `token`           | one LLM token chunk from `generate_node`       |
| `draft_replace`   | reflection rejected the draft — clear & re-stream |
| `content`         | full answer block (research path only — non-streamed) |
| `chat_context`    | final `{entity_ids, document_ids}` for the UI panel |
| `error`           | LLM or graph failure                           |

Tokens are filtered to come **only from `generate_node`** so reflection and
tool-call chunks never reach the user.

---

## 3. Skills

Skills decide *which system prompt and which slash-instruction* are used for
generation. All skills share the same tool set and reflection logic.

Skill definitions live in [skills.yaml](../backend/agent/prompts/skills.yaml)
— loaded once at process startup by
[prompt_service.py:_load_all](../backend/app/services/prompt_service.py#L38).

| Skill key                      | Prompt type                       | Slash command(s)                          | Purpose                                 |
|--------------------------------|-----------------------------------|-------------------------------------------|-----------------------------------------|
| `qa` (default)                 | `Chat Agent: System`              | —                                         | Default knowledge Q&A                   |
| `write_social_media_post`      | `Chat Skill: Social Media Post`   | `/write_social_media_post`                | New social posts from a doc             |
| `write_social_media_comment`   | `Chat Skill: Social Media Comment`| `/write_social_media_comment`, `/write_comment` | Comments/replies on a post        |
| `email_draft`                  | `Chat Skill: Email Draft`         | `/email`, `/email_draft`                  | Email drafting                          |
| `summary`                      | `Chat Skill: Summary`             | `/summary`, `/summarize`                  | Document/topic summarization            |
| `fact_check`                   | `Chat Skill: Fact Check`          | `/fact_check`                             | Claim verification (mandates web tools) |

A skill YAML entry is:

```yaml
- key: fact_check
  prompt_type: "Chat Skill: Fact Check"
  node_name: fact_check_generate_node
  description: "Fact checking and claim verification"
  slash_instruction: |
    Fact-check the document provided in the CURRENT CONTEXT above.
  prompt_text: |
    You are an expert fact-checker...
```

### Skill selection paths

1. **Slash command** — frontend strips `/<cmd>` from the input and adds
   `?skill=<key>` to the SSE URL. Backend
   ([chat.py route](../backend/app/api/routes/chat.py)) passes it as
   `skill_override` through `ChatAgentService.get_stream → build_research_graph
   → intent_node`. The intent node uses it verbatim and skips embedding match.
2. **Embedding match** — when no override is set, `match_skill()` embeds the
   message with Gemini (task type `SEMANTIC_SIMILARITY`) and picks the skill
   whose `description + slash_instruction` text has the highest cosine
   similarity ≥ 0.5. Below threshold → `default_skill = qa`.

### Adding a new skill

1. Add the `PromptType` enum value to
   [prompt_utils.py:13](../backend/app/services/prompt_utils.py#L13).
2. Add the prompt body to one of the YAMLs in
   [backend/agent/prompts/](../backend/agent/prompts/) (e.g. `chat.yaml`).
3. Add the skill entry to
   [skills.yaml](../backend/agent/prompts/skills.yaml) (key, prompt_type,
   node_name, description, slash_instruction, optional prompt_text fallback).
4. Wire the slash command into the frontend `SKILL_SHORTCUTS` map in
   `ChatPanel.vue` and `ChatInterface.vue`.

No code changes are needed in `research_graph.py` — `generate_node` reads
all skills from `get_all_skills()` and dispatches by `state["skill"]`.

> Note on `.agent/skills/skills.md`: this file is a separate registry of
> **Claude-Code-side** skills (`social-comment`, `extract-doc`, `kg-explore`,
> `chat-scope`) used by the local dev agent. It is unrelated to the chat
> agent's runtime skill set.

---

## 4. Tools

Tools are bound to the LLM via `llm.bind_tools(tools)` in `build_research_graph`.
All factories live in
[tools.py](../backend/app/chat_workflows/tools.py) (chat agent) and
[tavily_tools.py](../backend/app/chat_workflows/tavily_tools.py) (research
sub-agent).

### 4.1 Chat-agent tools

| Tool                       | Source                | Purpose                                              | Disabled when                       |
|----------------------------|-----------------------|------------------------------------------------------|-------------------------------------|
| `retrieve_documents_tool`  | `tools.py:30`         | Semantic search over the user's library              | Always available                    |
| `fetch_social_post_tool`   | `tools.py:145`        | Fetch a URL and extract OG metadata + main text      | Always available                    |
| `world_context_tool`       | `tools.py:235`        | Google CSE for recent news headlines about a topic   | `GOOGLE_SEARCH_API` / `GOOGLE_CSE_ID` unset |
| `google_search_tool`       | `tools.py:99`         | General Google CSE search to validate / augment      | Same as above                       |
| `knowledge_graph_tool`     | `tools.py:286`        | Entity + relationship lookup on `kg_node`/`kg_edge`  | Always available                    |

Construction in `ChatAgentService.get_stream`:

- `retrieve_tool` and `kg_tool` are built per-request with the session's
  `user_id`, `scope_type`, `scope_id`, and `db_session` (so the tool closure
  enforces user isolation and the chat's scope filter).
- `fetch_tool`, `world_tool`, `google_tool` are built inside
  `build_research_graph` since they don't need a DB session.

### 4.2 Searching the DB

`retrieve_documents_tool` → `DocumentService.get_relevant_documents_with_chunks_for_chat`
([document_service.py:906](../backend/app/services/document_service.py#L906)):

1. Embeds the query via `embedding_service.search_embeddings`
   ([embedding_service.py:547](../backend/app/services/embedding_service.py#L547)) —
   pgvector cosine-similarity scan against the `embedding` table filtered
   by `user_id` and `source_types=['document']`,
   `similarity_threshold=0.55`.
2. Groups matching chunks by `document_id`, keeps the top 5 chunks per
   document, sorts documents by their best chunk score, returns up to 5
   documents.
3. Strips HTML, truncates long chunks (~1500 chars) and falls back to
   document content (~2000 chars) when fewer chunks matched.

The returned string includes the `doc_id`, which the LLM is instructed to
wrap in `<source doc_id="N">` tags. The streaming layer regex-extracts those
IDs and ships them in the final `chat_context` event so the UI can pin the
source cards.

`knowledge_graph_tool` is a separate path: it does an `ilike '%query%'`
match on `kg_node.label` scoped by `user_id`, fetches edges joining matched
node IDs, and returns a formatted entity + relationship dump.

### 4.3 Searching the internet

Two providers, two roles:

- **Google CSE** (`google_search_tool`, `world_context_tool`) — used by the
  *chat* agent for ad-hoc verification and recent-news context inside any
  skill. `world_context_tool` is `google_search_tool` with the query
  appended with `"latest news"` and is the one `fact_check` and the social
  skills are told to prefer.
- **Tavily** (`tavily_search`, `tavily_extract`,
  [tavily_tools.py](../backend/app/chat_workflows/tavily_tools.py)) — used
  **only** by the research multi-agent sub-agents (see §5). Tavily returns
  ranked results plus clean markdown extraction, which is better suited to
  the "research and save to library" loop than Google CSE snippets.

Both providers are optional: if their API keys aren't set, the corresponding
factory returns `None` and the tool simply isn't bound.

### 4.4 Reflection (recap)

Not a tool — a graph node ([§2.6](#26-reflect_node--critique-loop)). It runs
after every non-tool-call generation, can fire up to 3 times per turn, uses
role-swap to act as a teacher grading the student answer, and either ends
the turn (`is_satisfactory=True`) or appends its critique as a
`HumanMessage` for the next `generate_node` pass.

---

## 5. Research Multi-Agent Workflow

Triggered when `intent_node` returns `requires_research=True` (the
intent-classification prompt decides; typically for "Find me X", "What is
the latest on Y", "Compare A and B" style queries).

Architecture: **Plan-and-Execute + Supervisor**
([research_multiagent_graph.py](../backend/app/chat_workflows/research_multiagent_graph.py)).

```
planner_node ──► supervisor_node ──► [Send fan-out] ──► subagent_node (×N)
                                                              │
                                                              ▼
                                                    coverage_critic_node
                                                          │
                                              loop back   │   ok
                                              ◄───────────┴──────────►
                                                                    writer_node ──► END
```

| Node                  | What it does                                                                                  |
|-----------------------|-----------------------------------------------------------------------------------------------|
| `planner_node`        | LLM splits the brief into 1–3 sub-topics (JSON `{topic, rationale}`). Caps `max_subagents=3`. |
| `supervisor_node`     | Anchor for the fan-out; logs/surfaces planner failures into `research_error`.                 |
| `subagent_node` (×N)  | Runs an independent ReAct loop per sub-topic (see below). Uses a fresh DB session.            |
| `coverage_critic_node`| LLM judge: do the findings cover the brief? Loops back to supervisor at most `max_critic_loops=1`. |
| `writer_node`         | Synthesizes a final answer with `[1] title — url` citations. Bypasses LLM and surfaces an error if no findings exist (prevents source hallucination). |

Each sub-agent ([research_subagent.py](../backend/app/chat_workflows/research_subagent.py))
is a small ReAct loop with three tools:

- `tavily_search` — ranked web results for the sub-topic.
- `tavily_extract` — clean markdown from a chosen URL (truncated to 3000 chars).
- `save_research_document` — creates a `Document` row, links it to the
  current `ResearchSession`, and fires off the same background pipeline
  bookmarks use (DSPy content analysis → embeddings → KG extraction).
  Capped at 3 docs per sub-agent.

Budget: `max_tool_calls_per_subagent=4`. After the budget is spent the
sub-agent is asked for a 2-3 sentence summary of what it found.

The dispatcher in the chat graph
([research_graph.py:529](../backend/app/chat_workflows/research_graph.py#L529))
also **reuses** an existing `ResearchSession` for the same `chat_session_id`
across follow-up turns, so a multi-turn research conversation accumulates
sources into one session rather than spawning a new session per question.

---

## 6. Prompts

All prompts are YAML files under [backend/agent/prompts/](../backend/agent/prompts/):

| File              | Contains                                                                 |
|-------------------|--------------------------------------------------------------------------|
| `chat.yaml`       | `Chat Agent: System`, `Chat Agent: Intent Classification`, `Chat Agent: Reflection`, `Chat Agent: Type-ahead Prompt` |
| `skills.yaml`     | Skill registry + per-skill `prompt_text` fallbacks                        |
| `research.yaml`   | `Chat Research: Planner`, `Chat Research: Subagent System`, `Chat Research: Coverage Critic`, `Chat Research: Writer` |
| `analysis.yaml`   | Doc analysis prompts (summary, entities, topics, etc.)                    |
| `extraction.yaml` | Source-type specific DSPy extraction prompts                              |
| `dspy.yaml`       | DSPy-side prompt templates                                                |
| `x_post.yaml`     | X/Twitter processing                                                      |

All loads go through `get_prompt(<PromptType>.value)`
([prompt_service.py:95](../backend/app/services/prompt_service.py#L95)).
Missing required prompts raise `ValueError` at graph-build time so the
process fails fast rather than silently falling back to inline strings.

> **Project rule** ([CLAUDE.md](../CLAUDE.md)): never inline prompts in
> Python — add the YAML entry and a `PromptType` enum value.

---

## 7. Where to start when changing the agent

| You want to…                                          | Edit…                                                                                  |
|-------------------------------------------------------|----------------------------------------------------------------------------------------|
| Tweak the default Q&A persona                         | `chat.yaml` → `Chat Agent: System`                                                     |
| Add a new skill (e.g. translation)                    | `skills.yaml` + frontend `SKILL_SHORTCUTS` (see §3)                                    |
| Add or remove an agent tool                           | [tools.py](../backend/app/chat_workflows/tools.py) + the `tools = […]` list in `build_research_graph` |
| Change when reflection retries                        | `route_after_reflect` in [research_graph.py:726](../backend/app/chat_workflows/research_graph.py#L726) and the `Chat Agent: Reflection` prompt |
| Change library search thresholds / chunking           | `get_relevant_documents_with_chunks_for_chat` in [document_service.py](../backend/app/services/document_service.py) |
| Adjust research budgets                               | `DEFAULT_MAX_SUBAGENTS`, `DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT`, `DEFAULT_MAX_CRITIC_LOOPS` in [research_multiagent_graph.py](../backend/app/chat_workflows/research_multiagent_graph.py) |
| Swap the web search provider                          | `get_google_search_tool` / `create_world_context_tool` in `tools.py`, or the Tavily client in `tavily_tools.py` |

---

## 8. Related docs

- [Map_Chat_Skill_Prompt_Nodes.md](../instructions/Map_Chat_Skill_Prompt_Nodes.md) — concise skill/prompt/node map
- [KG_Creation.md](../backend/KG_Creation.md) — knowledge graph extraction pipeline
- [CHAT_INTERFACE_REPLICATION_GUIDE.md](../instructions/CHAT_INTERFACE_REPLICATION_GUIDE.md) — frontend chat UI / SSE integration
- [CLAUDE.md](../CLAUDE.md) — prompts-in-YAML rule
