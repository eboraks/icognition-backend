# Agent Workflow

> **Branch: `Agent_Architecture_May_24`** — this document describes the
> simplified agent architecture that replaces the previous reflective
> research agent. See [§8 — Migration from the previous architecture](#8-migration-from-the-previous-architecture)
> for what changed and why.

End-to-end reference for the iCognition chat agent: how a user message flows
from the SSE endpoint through the LangGraph state machine, which tools the
agent can call, how skills are selected, how reflection works for skills
that opt in, how the agent searches the user's library, and how it
researches the open web on demand.

---

## 1. High-level Architecture

```
                                ┌─────────────────────────┐
   POST /chat/stream ──────────►│ ChatAgentService.get_   │
   (SSE, with optional ?skill=) │ stream()                │
                                └──────────┬──────────────┘
                                           │
                                           │  state-snapshot-before,
                                           │  stream tokens,
                                           │  state-snapshot-after
                                           ▼
                                ┌─────────────────────────┐
                                │ build_research_graph()  │  ← Chat Agent
                                │ (LangGraph StateGraph)  │
                                └──────────┬──────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                              ▼
        normal path (qa, social,                       skill = "research"
         summary, fact_check, …)                       (only via /research)
                    │                  ┌──────────────────────────────┐
                    │                  │ build_research_multiagent_   │
                    │                  │ graph() — Plan + Execute +   │
                    │                  │ Supervisor (Tavily subagents)│
                    │                  └──────────────────────────────┘
                    ▼
        SSE events: token, status, draft_replace (reflection skills
        only), done(with chat_context), error
```

Two graphs are involved:

1. **Chat Agent** ([research_graph.py](../backend/app/chat_workflows/research_graph.py)) —
   serves every chat message. One generate node, KG enrichment, tools loop,
   and an **opt-in** reflection loop. No intent classifier.
2. **Research Multi-Agent** ([research_multiagent_graph.py](../backend/app/chat_workflows/research_multiagent_graph.py)) —
   a sub-graph dispatched **only when the user types `/research`**. Plans
   sub-topics, runs Tavily-powered sub-agents in parallel, critiques
   coverage, writes a synthesized response with citations, and saves the
   source documents to the user's library.

Entry point: `ChatAgentService.get_stream` in
[chat_agent_service.py](../backend/app/services/chat_agent_service.py).
It loads the chat session, builds session-scoped tools, fetches prompts,
retrieves the Postgres checkpointer, compiles the graph, takes a state
snapshot before invocation, streams tokens to the client, and takes a
second state snapshot at the end to emit the canonical answer + context.

---

## 2. The Chat Agent

### 2.1 Graph nodes

```
START
  │
  ▼
┌────────────────┐
│ generate_node  │ ◄────────────────┐
│  (KG enrich +  │                  │
│   LLM + tools) │                  │
└────────┬───────┘                  │
         │                          │
         ▼                          │
   ┌───────────────────────┐        │
   │ route_after_generate  │        │
   └────┬──────────────┬───┘        │
        │              │            │
        │ tool_calls?  │ no         │
        ▼              ▼            │
   ┌────────┐    ┌──────────────────┴─┐
   │ tools  │───►│ skill.reflect?     │
   │(ToolNode)   └──┬───────────────┬─┘
   └────────┘      yes              no
                   │                 │
                   ▼                 ▼
            ┌─────────────┐         END
            │ reflect_node │
            └──────┬──────┘
                   │
                   ▼
           ┌──────────────────┐
           │ route_after_     │
           │ reflect          │
           └─┬────────────┬───┘
             │            │
       satisfied?    retry (≤3)
             ▼            └─────────►
            END
```

State definition: `AgentState` in
[research_graph.py](../backend/app/chat_workflows/research_graph.py).
Key fields: `messages`, `skill`, `latest_query`,
`context_document_ids`, `is_satisfactory`, `reflection_count`.

Notable removals from the previous architecture: there is no `intent_node`,
no `intent_description`, no `requires_research` flag, no
`dispatch_research_node` reachable from `intent_node`, and no
deterministic KG enrichment step before the LLM call. KG context now flows
through `knowledge_graph_tool` (an on-demand tool the LLM calls when it
wants entity/relationship context) — see §4.1.

### 2.2 generate_node — prompt resolution, LLM call

The single generate node handles everything the LLM needs:

1. **Skill resolution.** The skill comes from the SSE query param
   `?skill=<key>` (slash command) and defaults to `qa`. The skill key
   indexes into the YAML-loaded skill registry; that yields the system
   prompt and tools list to bind.
2. **System prompt assembly.** The skill's system prompt already contains
   the response-style guidance that used to live in the intent
   classifier (e.g. "this user is asking about a document — answer
   directly; this user is requesting an action — produce the artifact").
   Its tool-usage rules instruct the LLM to call `knowledge_graph_tool`
   for entity-centric questions and `retrieve_documents_tool` for
   library lookups.
3. **Slash-command bare-message rewrite.** If the user message is just a
   bare slash command (e.g. `/fact_check` with no body), the skill's
   `slash_instruction` replaces it so the LLM has something concrete to
   act on.
4. **LLM call.** `llm_with_tools.ainvoke(...)` with the assembled
   messages. Gemini's `MALFORMED_FUNCTION_CALL` is retried once without
   tools.

### 2.3 Tools loop

If `route_after_generate` sees `tool_calls`, the prebuilt LangGraph
`ToolNode` executes them, appends `ToolMessage` results, and edges back
to `generate_node`. The same skill prompt is used again — only the
message history changes.

### 2.4 reflect_node — opt-in per skill

`route_after_generate` routes to `reflect_node` **only if the active
skill has `reflect: true`**; otherwise the graph goes straight to END.

When `reflect: true`:

- The reflector extracts only the latest human/AI pair from the history
  to avoid confusing it with prior turns.
- Role-swap: the AI's answer is fed as a `HumanMessage` and the user's
  question as an `AIMessage`, framing the LLM as a teacher grading a
  student submission.
- Runs `Chat Agent: Reflection` with
  `with_structured_output(ReflectionOutput)` —
  `{critique, needs_search, search_query, is_satisfactory}`.
- If unsatisfied, the `critique` is appended as a `HumanMessage` so the
  next `generate_node` pass sees it and can revise.

`route_after_reflect` ends the turn when `is_satisfactory=True` or
`reflection_count > 3`, otherwise routes back through `generate_node`.

For skills with `reflect: false` (the default for `qa`, `email_draft`,
`write_social_media_*`), the first draft is returned as-is.

### 2.5 Streaming protocol — state-snapshot-before / snapshot-after

The streaming loop in `ChatAgentService.get_stream` follows a single
pattern: **tokens stream live for UX; the agent state is the source of
truth for the canonical answer.**

```python
config = {"configurable": {"thread_id": thread_id}}

# 1. Snapshot before this turn runs — anchor for "what's new".
prior = await agent.aget_state(config)
prior_last_ai_id = _last_ai_message_id(prior.values.get("messages", []))

streamed_any_token = False
last_intent_status = None

# 2. Stream tokens live; values events drive status + draft_replace.
async for stream_type, data in agent.astream(
    {"messages": input_messages}, config=config,
    stream_mode=["messages", "values"],
):
    if stream_type == "messages":
        # LangGraph 1.0+: "messages" only emits LLM tokens from THIS
        # invocation. No replay of checkpointed history. Stream them.
        chunk, meta = data
        if (
            meta.get("langgraph_node") == "generate_node"
            and isinstance(chunk, AIMessageChunk)
            and not chunk.tool_call_chunks
            and chunk.content
        ):
            streamed_any_token = True
            yield {"type": "token", "content": _text(chunk.content)}

    elif stream_type == "values":
        # values events only drive: status pings + draft_replace on
        # reflection rejection. NOT the final answer.
        for event in _status_events(data, prior_last_ai_id, last_intent_status):
            last_intent_status = event.get("intent")
            yield event

        if _was_draft_rejected(data, prior_last_ai_id):
            yield {"type": "draft_replace"}
            streamed_any_token = False

# 3. Snapshot after — canonical answer comes from state, not stream.
final = await agent.aget_state(config)
answer_msg = _latest_new_ai_message(final.values["messages"], prior_last_ai_id)

if answer_msg is None:
    yield {"type": "error", "content": "Failed to generate a response."}
    return

answer = _text(answer_msg.content)

# If tokens didn't stream (research path), deliver the answer as one block.
if not streamed_any_token:
    yield {"type": "content", "content": answer}

yield {
    "type": "done",
    "entity_ids": list(set(final.values.get("context_entity_ids", []))),
    "document_ids": list(set(int(m) for m in re.findall(
        r'<source\s+doc_id=["\'](\d+)["\']>', answer))),
}
```

Two `aget_state` calls per turn (one DB roundtrip each) — kept as the
default to avoid the bug class where stale checkpoint values race with
the current turn's writes. No caching gymnastics.

SSE events emitted to the frontend:

| Event type        | When                                                           |
|-------------------|----------------------------------------------------------------|
| `status`          | UI hint (e.g. "researching the web")                           |
| `token`           | one LLM token chunk from `generate_node`                       |
| `draft_replace`   | reflection rejected the draft — clear and re-stream (reflect skills only) |
| `content`         | full answer block (research path only — non-streamed)          |
| `done`            | `{entity_ids, document_ids}` for the UI panel; signals stream end |
| `error`           | LLM or graph failure                                           |

Tokens are filtered to come **only from `generate_node`** so reflection
and tool-call chunks never reach the user.

---

## 3. Skills

Skills decide *which system prompt, which tools, and whether reflection
runs*. Slash commands are the only way to switch skills.

Skill definitions live in [skills.yaml](../backend/agent/prompts/skills.yaml)
and are loaded once at process startup by
[prompt_service.py](../backend/app/services/prompt_service.py)
(`_load_all`).

| Skill key                      | Prompt type                       | Slash command(s)                          | Reflect | Purpose                                |
|--------------------------------|-----------------------------------|-------------------------------------------|---------|----------------------------------------|
| `qa` (default)                 | `Chat Agent: System`              | —                                         | `false` | Default knowledge Q&A                  |
| `write_social_media_post`      | `Chat Skill: Social Media Post`   | `/write_social_media_post`                | `false` | New social posts from a doc            |
| `write_social_media_comment`   | `Chat Skill: Social Media Comment`| `/write_social_media_comment`, `/write_comment` | `false` | Comments/replies on a post         |
| `email_draft`                  | `Chat Skill: Email Draft`         | `/email`, `/email_draft`                  | `false` | Email drafting                         |
| `summary`                      | `Chat Skill: Summary`             | `/summary`, `/summarize`                  | `true`  | Document/topic summarization           |
| `fact_check`                   | `Chat Skill: Fact Check`          | `/fact_check`                             | `true`  | Claim verification (mandates web tools)|
| `research`                     | `Chat Research: Planner` (entry)  | `/research`                               | n/a     | Multi-agent web research (sub-graph)   |

A skill YAML entry now includes the `reflect` flag:

```yaml
- key: fact_check
  prompt_type: "Chat Skill: Fact Check"
  description: "Fact checking and claim verification"
  reflect: true            # NEW — opt-in reflection loop
  slash_instruction: |
    Fact-check the document provided in the CURRENT CONTEXT above.
  prompt_text: |
    You are an expert fact-checker...
```

### Skill selection — slash commands only

There is **no embedding-based skill matching and no intent classifier**.
Slash commands are the only way to switch skills:

1. The frontend's `SKILL_SHORTCUTS` map intercepts `/<cmd>` at the input
   and strips it from the message, then adds `?skill=<key>` to the SSE
   URL.
2. The chat route passes `skill` through to
   `ChatAgentService.get_stream → build_research_graph`.
3. `generate_node` resolves `state["skill"]` (defaults to `qa`).

The `/research` slash command is special: it routes through
`dispatch_research_node` into the multi-agent sub-graph instead of
through `generate_node` (see §5).

### Adding a new skill

1. Add the `PromptType` enum value in
   [prompt_utils.py](../backend/app/services/prompt_utils.py).
2. Add the prompt body to one of the YAMLs in
   [backend/agent/prompts/](../backend/agent/prompts/).
3. Add the skill entry to
   [skills.yaml](../backend/agent/prompts/skills.yaml) (key, prompt_type,
   description, slash_instruction, optional prompt_text fallback,
   **`reflect: true|false`**).
4. Wire the slash command into the frontend `SKILL_SHORTCUTS` map in
   `ChatPanel.vue` and `ChatInterface.vue`.

---

## 4. Tools

Tools are bound to the LLM via `llm.bind_tools(tools)` in
`build_research_graph`. All factories live in
[tools.py](../backend/app/chat_workflows/tools.py) (chat agent) and
[tavily_tools.py](../backend/app/chat_workflows/tavily_tools.py).

### 4.1 Chat-agent tools

| Tool                       | Source             | Purpose                                                | Disabled when             |
|----------------------------|--------------------|--------------------------------------------------------|---------------------------|
| `retrieve_documents_tool`  | `tools.py`         | Semantic search over the user's library                | Always available          |
| `fetch_social_post_tool`   | `tools.py`         | Fetch a URL and extract OG metadata + main text        | Always available          |
| `tavily_search`            | `tavily_tools.py`  | Ranked web search; used for verification and recent context | `TAVILY_API_KEY` unset |
| `tavily_extract`           | `tavily_tools.py`  | Clean markdown extraction from a single URL            | `TAVILY_API_KEY` unset    |
| `knowledge_graph_tool`     | `tools.py`         | Entity + relationship lookup on `kg_node`/`kg_edge`    | Always available          |

**Google CSE has been removed.** `google_search_tool` and
`world_context_tool` no longer exist. Tavily is the single web-search
provider for both the chat agent and the research sub-agents. Tavily's
ranked search + clean extraction covers the use cases that previously
needed two providers.

Construction in `ChatAgentService.get_stream`:

- `retrieve_tool` and `kg_tool` are built per-request with the session's
  `user_id`, `scope_type`, `scope_id`, and `db_session` (so the tool
  closure enforces user isolation and the chat's scope filter).
- `fetch_tool`, `tavily_search`, `tavily_extract` are built inside
  `build_research_graph` since they don't need a DB session.

### 4.2 Searching the DB

`retrieve_documents_tool` →
`DocumentService.get_relevant_documents_with_chunks_for_chat` in
[document_service.py](../backend/app/services/document_service.py):

1. Embeds the query via `embedding_service.search_embeddings` —
   pgvector cosine-similarity scan against the `embedding` table filtered
   by `user_id` and `source_types=['document']`,
   `similarity_threshold=0.55`.
2. Groups matching chunks by `document_id`, keeps the top 5 chunks per
   document, sorts documents by their best chunk score, returns up to 5
   documents.
3. Strips HTML, truncates long chunks (~1500 chars) and falls back to
   document content (~2000 chars) when fewer chunks matched.

The returned string includes the `doc_id`, which the LLM is instructed
to wrap in `<source doc_id="N">` tags. The streaming layer regex-extracts
those IDs and ships them in the final `done` event so the UI can pin
the source cards.

`knowledge_graph_tool` is a separate path: `ilike '%query%'` match on
`kg_node.label` scoped by `user_id`, fetches edges joining matched node
IDs, and returns a formatted entity + relationship dump.

### 4.3 Searching the internet — Tavily only

Tavily ([tavily_tools.py](../backend/app/chat_workflows/tavily_tools.py))
is now the single web-search provider for both the chat agent and the
research sub-agents:

- `tavily_search(query, topic="general"|"news")` — ranked results with
  snippets. `topic="news"` is used by skills that need recent context
  (the old `world_context_tool` role).
- `tavily_extract(url)` — clean markdown content for a URL, used by the
  research sub-agents and by skills that need full content for a single
  source.

If `TAVILY_API_KEY` is unset, both factories return `None` and the
tools simply aren't bound. The chat agent still works (it just can't
hit the web).

---

## 5. Research Multi-Agent Workflow

Triggered **only** when the user types `/research` (no auto-dispatch).
The chat agent receives `skill="research"`, and `generate_node` short-
circuits into `dispatch_research_node` which invokes the sub-graph.

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
- `tavily_extract` — clean markdown from a chosen URL (truncated to
  3000 chars).
- `save_research_document` — creates a `Document` row, links it to the
  current `ResearchSession`, and fires off the same background pipeline
  bookmarks use (DSPy content analysis → embeddings → KG extraction).
  Capped at 3 docs per sub-agent.

Budget: `max_tool_calls_per_subagent=4`. After the budget is spent the
sub-agent is asked for a 2-3 sentence summary of what it found.

The dispatcher reuses an existing `ResearchSession` for the same
`chat_session_id` across follow-up turns, so a multi-turn research
conversation accumulates sources into one session rather than spawning
a new session per question.

---

## 6. Prompts

All prompts are YAML files under
[backend/agent/prompts/](../backend/agent/prompts/):

| File              | Contains                                                                 |
|-------------------|--------------------------------------------------------------------------|
| `chat.yaml`       | `Chat Agent: System` (with intent-style guidance baked in), `Chat Agent: Reflection`, `Chat Agent: Type-ahead Prompt` |
| `skills.yaml`     | Skill registry — `key`, `prompt_type`, `description`, `slash_instruction`, `prompt_text` fallback, **`reflect: bool`** |
| `research.yaml`   | `Chat Research: Planner`, `Chat Research: Subagent System`, `Chat Research: Coverage Critic`, `Chat Research: Writer` |
| `analysis.yaml`   | Doc analysis prompts (summary, entities, topics, etc.)                    |
| `extraction.yaml` | Source-type specific DSPy extraction prompts                              |
| `dspy.yaml`       | DSPy-side prompt templates                                                |
| `x_post.yaml`     | X/Twitter processing                                                      |

Removed from `chat.yaml`: `Chat Agent: Intent Classification`. That
behavior is now folded into `Chat Agent: System` (and into each skill's
`prompt_text` for skill-specific guidance).

All loads go through `get_prompt(<PromptType>.value)`
([prompt_service.py](../backend/app/services/prompt_service.py)).
Missing required prompts raise `ValueError` at graph-build time so the
process fails fast rather than silently falling back to inline strings.

> **Project rule** ([CLAUDE.md](../CLAUDE.md)): never inline prompts in
> Python — add the YAML entry and a `PromptType` enum value.

---

## 7. Where to start when changing the agent

| You want to…                                          | Edit…                                                                                  |
|-------------------------------------------------------|----------------------------------------------------------------------------------------|
| Tweak the default Q&A persona                         | `chat.yaml` → `Chat Agent: System`                                                     |
| Add a new skill                                       | `skills.yaml` + frontend `SKILL_SHORTCUTS` (see §3). Decide `reflect: true|false`.     |
| Turn reflection on/off for an existing skill          | Flip `reflect:` in `skills.yaml`                                                       |
| Add or remove an agent tool                           | [tools.py](../backend/app/chat_workflows/tools.py) + the `tools = […]` list in `build_research_graph` |
| Change library search thresholds / chunking           | `get_relevant_documents_with_chunks_for_chat` in [document_service.py](../backend/app/services/document_service.py) |
| Adjust research budgets                               | `DEFAULT_MAX_SUBAGENTS`, `DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT`, `DEFAULT_MAX_CRITIC_LOOPS` in [research_multiagent_graph.py](../backend/app/chat_workflows/research_multiagent_graph.py) |
| Swap the web-search provider                          | `tavily_tools.py` (Tavily is the only provider; Google CSE has been removed)            |

---

## 8. Migration from the previous architecture

This section documents what changed relative to the pre-`Agent_Architecture_May_24`
implementation, and why.

| Removed                                                  | Replaced by                                                                                       | Why |
|----------------------------------------------------------|---------------------------------------------------------------------------------------------------|-----|
| `intent_node` (LLM classifier on every turn)             | Intent guidance folded into `Chat Agent: System` and per-skill `prompt_text`                       | One LLM round-trip per turn was paying for a routing decision that slash commands + a single system prompt already cover. Saves ~1s latency per turn and eliminates the entire class of misclassification bugs. |
| Embedding-based `match_skill()` fallback                 | Slash commands only; default `qa` for everything else                                              | Skill selection was already deterministic when users used slash commands. The embedding fallback added cost and unpredictability. |
| `requires_research` auto-dispatch                        | `/research` slash command                                                                          | Auto-classifying "this needs deep research" surprised users with 30-second responses. `/research` makes the expensive path explicit and user-controlled. |
| Reflection on every turn (`reflect_node` always runs)    | `reflect: bool` flag per skill in `skills.yaml`                                                    | Critique-and-retry was doubling latency on the 80% of turns that didn't need it. Now only `summary`, `fact_check`, and research opt in. |
| `google_search_tool`, `world_context_tool` (Google CSE)  | Tavily (`tavily_search` with `topic="general"|"news"`)                                             | Two providers existed for historical reasons. Tavily covers both ranked search and clean extraction, so one provider is enough. Less config, fewer branches. |
| `is_satisfactory` polling + `has_yielded_content` + `_latest_ai_answer` heuristic in `get_stream` | State-snapshot-before / state-snapshot-after via `aget_state(config)` | The old loop tried to reconstruct turn boundaries from event streams; the snapshot pair makes the boundary explicit, killing the "previous turn's answer leaks into this turn" bug. |
| `end_stream` event with full-text re-replay              | `done` event with `{entity_ids, document_ids}` only                                                 | The end-of-stream payload duplicating the streamed text existed only to recover from drift between server and client accumulators. With state-as-truth that drift is impossible. |
| Deterministic KG enrichment inside `generate_node` (`_enrich_kg`, `resolve_entities_from_query`, `extracted_entities` / `kg_context` / `context_entity_ids` state fields) | The LLM calls `knowledge_graph_tool` on demand; the system prompt instructs it to use the tool for entity-centric questions | Pre-enriching needed something to identify "the entities the user is asking about." The pre-refactor LLM intent classifier produced that; without it, the only options were a regex hack or a dedicated LLM call. Letting the LLM call the existing KG tool when it judges KG context useful is cleaner — and the tool returns richer results than the pre-enriched block did. Trade-off: the `chat_context.entity_ids` payload is empty under the new model; entity pinning in the UI would need to be re-derived from tool output if you want it back. |

What is preserved:

- LangGraph + Postgres checkpointer for conversation memory.
- YAML-backed prompts with the `get_prompt()` interface.
- The research multi-agent sub-graph itself (plan → supervisor → fan-out
  → critic → writer).
- The `knowledge_graph_tool` itself (on-demand).
- The skill abstraction (one system prompt + tools per skill key).
- SSE as the streaming transport (with a simpler event schema).

---

## 9. Related docs

- [Map_Chat_Skill_Prompt_Nodes.md](../instructions/Map_Chat_Skill_Prompt_Nodes.md) — concise skill/prompt/node map (predates this refactor; may be out of date)
- [KG_Creation.md](../backend/KG_Creation.md) — knowledge graph extraction pipeline
- [CHAT_INTERFACE_REPLICATION_GUIDE.md](../instructions/CHAT_INTERFACE_REPLICATION_GUIDE.md) — frontend chat UI / SSE integration
- [CLAUDE.md](../CLAUDE.md) — prompts-in-YAML rule
