# iCognition — Implementation Plan

**Approach**: Infrastructure first → UI unification → Social comment writing → Knowledge graph
**Tracking**: Check off tasks as completed (`- [x]`). Each phase has a clear test gate before moving on.

---

## Phase 1 — Performance Infrastructure
*Goal: Document ingestion is fast and non-blocking. Agent responses are faster.*

### 1.1 Fix SQL Injection Risk in `search_embeddings`
**File**: `backend/app/services/embedding_service.py` (lines 829–863)
**Problem**: Vector and source_types built via f-string interpolation in raw SQL.
**Fix**: Use SQLAlchemy `text()` with proper parameter binding for all dynamic values.

- [x] Replace f-string vector interpolation with a parameterized cast (`CAST(:query_vector AS vector)`)
- [x] Replace `source_types_str` construction with named bindparams (`:source_type_0`, `:source_type_1`, ...)
- [ ] Add a unit test: `tests/test_embedding_service.py::test_search_embeddings_parameterized`

**Test gate**: Run `backend/tests/` — no SQL injection warnings from SQLAlchemy in logs.

---

### 1.2 Fix DB Session Leak in `ChatAgentService.get_suggestion`
**File**: `backend/app/services/chat_agent_service.py` (lines 133–134)
**Problem**: Manual `__anext__()` call bypasses the async context manager; session can leak.
**Fix**: Refactor to use `async with` session pattern, matching how `get_stream` handles it.

- [x] Replace manual generator driving with `async for db_session in get_session():` pattern
- [x] Move `from app.services.prompt_utils import PromptType` to file-level imports (removed 2 inline occurrences)
- [x] Removed duplicate `from app.services.document_service import DocumentService` import

**Test gate**: Call `/api/v1/chat/sessions/{id}/suggest` 20 times rapidly; verify DB connection pool stays stable (check `pg_stat_activity`).

---

### 1.3 Parallelize Chunk Embeddings with `asyncio.gather`
**File**: `backend/app/services/embedding_service.py` (lines 659–679)
**Problem**: Chunks embedded sequentially; a 10-chunk doc = 10+ serial Gemini API calls.
**Fix**: Gather all chunk embedding tasks concurrently.

- [x] Collect all (field, text) pairs for title + chunks, then run `asyncio.gather(*tasks)` once
- [x] `return_exceptions=True` so one failed chunk doesn't abort all others
- [x] Added timing log: `"Generated N embeddings … concurrently in Xs"`

**Test gate**: A 2000-word document should embed in under 5 seconds (vs ~15s sequential).

---

### 1.4 Reuse `dspy.LM` Instance (Stop Recreating Per Call)
**File**: `backend/app/services/dspy_content_service.py` (lines 222, 280)
**Problem**: `dspy.LM(self.model_name, api_key=...)` created on every `analyze_document_content()` call.
**Fix**: Initialize the LM instance once in `__init__`, store on `self.lm`.

- [x] Added `self.lm = dspy.LM(...)` to `DspyContentService.__init__()`, removed 2 per-call instantiations
- [x] Added `self.lm = dspy.LM(...)` to `DspyEntityService.__init__()`, removed per-call instantiation
- [x] Both services now use `dspy.context(lm=self.lm)` in their extraction methods

**Test gate**: Add a log in `__init__` and verify it appears only once at startup, not per extraction call.

---

### 1.5 Cache Prompts In-Memory with TTL
**File**: `backend/app/services/prompt_service.py` and `backend/app/chat_workflows/research_graph.py`
**Problem**: Every graph node (`intent_node`, `generate_node`, `reflect_node`) hits the DB to fetch its prompt. With 3 reflections, that's 9 DB reads per chat message.
**Fix**: Add a simple TTL cache (e.g., 5-minute expiry) to `PromptService.get_latest_prompt()`.

- [x] Added module-level `_prompt_cache` dict + `_CACHE_TTL = 300s` to `prompt_service.py`
- [x] `get_latest_prompt()` returns from cache if fresh; falls back to DB and populates cache
- [x] Returns `SimpleNamespace` so all callers work unchanged (`.system_prompt`, `.user_prompt`, `.version`)
- [x] Added `invalidate_prompt_cache(prompt_type)` and called it in `create_prompt` after commit

**Test gate**: Enable SQLAlchemy query logging and confirm only 1 prompt DB read per prompt type per chat request (not 3+).

---

### 1.6 Parallelize Content Extraction + Entity Extraction ✅
**File**: `backend/app/api/routes/bookmarks.py`
**Problem**: DSPy content extraction and entity extraction run sequentially.
**Fix**: Run both concurrently with `asyncio.gather` since they have no data dependency.

- [x] Identified sequential calls — both happened inside background task functions in `bookmarks.py`
- [x] `_process_document_content_and_entities()` wraps both in `asyncio.gather(return_exceptions=True)`
- [x] Main bookmark processing path uses `create_task()` for content, entities, and embeddings — all three fire concurrently
- [x] Entity extractor receives the raw document `content` field directly (not DSPy output) — no dependency

**Test gate**: Log timestamps for both operations; they should start within 100ms of each other.

---

### 1.7 Background Task Queue for Document Processing
**File**: `backend/app/api/routes/documents.py`
**Problem**: Document fetch → extract → embed pipeline blocks the HTTP response for 10–30s.
**Fix**: Return `202 Accepted` immediately, process in background, notify client via WebSocket/SSE.

- [x] Added `BackgroundTasks` to `POST /documents/`; URL case creates a stub document immediately
- [x] `POST /documents/` returns 202 for all paths; AI extraction always runs in background
- [x] Added `GET /documents/{id}/status` endpoint returning `"processing"` / `"ready"` / `"failed"`
- [x] Fixed `POST /bookmarks/` URL-only path (iPhone app): stub document + `_fetch_url_and_process_document` replaces synchronous `create_document_from_url()` call
- [x] Added `_fetch_url_and_process_document` background task in `bookmarks.py` (fetch URL → content+entity extraction → embeddings)
- [ ] Update chrome extension `background.js` to poll `GET /documents/{id}/status` as fallback when WebSocket notification is missed

**Test gate**: `POST /documents` with a URL should return within 500ms. Status should progress to `ready` within 30s.

---

### Phase 1 Complete Checklist
- [ ] All unit tests pass: `cd backend && .venv/bin/python -m pytest tests/`
- [ ] No deprecated method warnings in logs during a full document ingestion flow
- [ ] A 2000-word document ingests (fetch + extract + embed) in under 10 seconds

---

## Phase 1.B — Chrome Extension: Tab State Stability
*Goal: Fix 4 confirmed bugs causing analysis to disappear, wrong bookmarks to show, and double API calls.*

### Background: Confirmed Bugs from Log Analysis (2026-03-02)

From the session logs three bugs converge to produce the "analysis disappears" symptom:

```
"Saving document ID for URL: https://www.wsj.com/business"       ← Bug #2: wrong URL captured
Tab change to: .../what-to-know-about-the-live-nation...          ← State reset (correct)
Tab updated fires: ...?mod=business_lead_story                    ← Bug #1: query param = 2nd reset
Backend: 2x GET /bookmarks/find 40ms apart                        ← Bug #3: double event handling
Backend: 2x 404 response                                          ← Bug #4: async response overwrites state
```

---

### 1.B.1 Fix `cleanUrl()` to Strip Query Parameters ✅
**File**: `chrome-extension/src/components/Popup.vue` — `handleTabChange` dedup check
**Root cause**: `cleanUrl()` already strips query params via regex. The bug was in `handleTabChange`
comparing raw URLs (`active_tab.value?.url === tab.url`) instead of cleaned ones.

**Fix applied** (`Popup.vue:614`): Changed dedup check to compare cleaned URLs:
```javascript
if (cleanUrl(active_tab.value?.url || '') === cleanUrl(tab.url || '')) { return; }
```

- [x] Located root cause: dedup check used raw URL comparison, not cleaned URL
- [x] Fixed: `handleTabChange` now compares `cleanUrl(...)` on both sides
- [x] Test: open a WSJ article, let it fully load, confirm analysis does NOT disappear when the URL gains `?mod=...`
- [x] Test: two different articles on same domain still get separate cache entries

**Test gate**: Open a WSJ article, wait 5 seconds (for `?mod=` to be appended). Analysis should remain
visible; "Analyze This Page" button should NOT reappear.

---

### 1.B.2 Fix Double Event Handling (onActivated + onUpdated both trigger handleTabChange) ✅
**File**: `chrome-extension/src/components/Popup.vue` — `onUpdated` listener
**Root cause**: `onUpdated` fired for ANY tab (including background tabs), triggering a full
state reset even when the user's visible tab hadn't changed.

**Fix applied** (`Popup.vue:536`): `onUpdated` listener now queries the active tab before calling
`handleTabChange`, only proceeding when the updated tab is actually the active one:
```javascript
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.url) {
        const activeTabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (activeTabs[0]?.id === tabId) { handleTabChange(tab); }
    }
});
```
The cleaned-URL dedup check in `handleTabChange` (1.B.1) eliminates residual double-fires.

- [x] Fixed `onUpdated` to only fire for the currently active tab
- [x] Dedup check in `handleTabChange` collapses any remaining rapid-succession calls for same URL
- [x] Verify in backend logs: only 1 `GET /bookmarks/find` per page load

**Test gate**: Navigate to any page; backend should show exactly 1 bookmark search request per page,
never 2 back-to-back requests for the same URL.

---

### 1.B.3 Fix Async Operations Not Verifying Active Tab on Completion (Race Condition)
**File**: `chrome-extension/src/App.vue` / `Popup.vue` (all async functions that update global state)
**Root cause**: The extension stores all current-page state in global `ref` variables
(`document_summary`, `bookmark`, `doc`, `currentChatSessionId`). Async operations (bookmark fetch,
`searchBookmarksByUrl`, `handleNewDoc`, `initializeChatSession`) capture NO reference to which tab
they were started for. When they complete, they write to global state unconditionally — even if the
user switched tabs in the meantime.

**Confirmed leakage scenarios:**
- `searchBookmarksByUrl(tabB)` starts → user switches to tabC → tabB's document summary written to screen
- `handleNewDoc()` fires for an analysis triggered on tabA → user switched to tabB → tabA's analysis displays on tabB
- `initializeChatSession()` sets `currentChatSessionId` to wrong session → chat sends to wrong document

**Fix pattern — Operation Token (Cancellation Guard)**:
Introduce a single `operationToken` counter. Each time `handleTabChange` runs (true tab change),
increment the token. Every async function captures the token value at its start. Before writing to
global state, it checks `if (token !== currentToken) return` (stale result, discard).

```javascript
// In Popup.vue script setup:
let _opToken = 0
const getToken = () => ++_opToken
const isCurrentToken = (t) => t === _opToken

// Usage pattern:
const searchBookmarksByUrl = async (url) => {
  const token = getToken()
  // ... await long operations ...
  if (!isCurrentToken(token)) return  // tab changed, discard
  document_summary.value = result     // safe to write
}
```

- [x] Added `_opToken`, `advanceToken()`, `captureToken()`, `isCurrentToken()` helpers to `Popup.vue`
- [x] `handleTabChange` calls `advanceToken()` after passing validation (real tab change)
- [x] `searchBookmarksByUrl()`: captures token at start, guards state after each `await`
- [x] `handleNewDoc()`: uses `request.data.url` for caches; only updates display state if doc URL matches current tab
- [x] `initializeChatSession()`: captures token, guards `currentChatSessionId` assignment after `sendMessage`

**Test gate**:
1. Start analyzing Tab A (slow page)
2. Immediately switch to Tab B
3. Tab A's analysis should NOT appear on Tab B
4. Tab B should show "Analyze This Page" or its own cached analysis

---

### 1.B.4 Fix Document ID Saved Against Wrong URL
**File**: `chrome-extension/src/App.vue` / `Popup.vue` (cache-save logic after bookmark creation)
**Root cause**: "Saving document ID for URL: https://www.wsj.com/business" in the logs shows
the document ID being cached against the domain root, not the article URL. This happens because
`active_tab.value.url` is read at cache-save time, but `active_tab.value` still holds the URL from
the *previous* state of the tab (before the article URL was captured by `handleTabChange`).

The cache-save block reads:
```javascript
const cleanedUrl = cleanUrl(active_tab.value.url)   // may still be domain root
documentIdsByUrl.value[cleanedUrl] = doc.value.id
```

**Fix**: When saving a newly-created document's ID, use the URL that was passed INTO the
create/analyze flow (captured at click time), not `active_tab.value.url` read from live state.

- [x] In `createBookmark()`: capture `const targetUrl = cleanUrl(active_tab.value.url)` before `sendMessage`
- [x] All cache writes in `.then()` callback use `targetUrl` instead of re-reading `active_tab.value.url`

**Test gate**: "Saving document ID for URL:" log should always show the full article URL, never
just the domain root.

---

### 1.B.5 Fix Wrong Tab Captured When User Has Two Chrome Windows
**File**: `chrome-extension/src/components/Popup.vue` — `onMounted` tab listeners
**Problem**: When the user has two Chrome windows open (e.g. Window A = X.com post, Window B = Langfuse),
clicking "Analyze This Page" bookmarks the wrong page.

**Root cause**: `chrome.tabs.onActivated` fires when the active tab *within* a window changes, but
does **not** fire when the user switches *focus between windows*. If X.com was already the active
tab in Window A, switching to Window A from Window B does not trigger any tab event. `active_tab`
stays pointed at the Langfuse tab from Window B.

Confirmed in backend logs (2026-03-02):
```
Creating bookmark for URL: http://localhost:3000/auth/sign-in
```
The user intended to analyze the X.com post — the side panel was associated with the iCognition
frontend window and `active_tab` never updated when the user switched to the X.com window.

**Fix**: Do a fresh `chrome.tabs.query({ active: true, currentWindow: true })` at click time inside
`handleBookmark()`, rather than relying on the pre-stored `active_tab` state. The side panel is
attached to a specific browser window; querying at click time always returns the correct tab for
that window, regardless of any missed state updates. Also update `active_tab` with the result so
the rest of the flow works correctly.

```javascript
const handleBookmark = async () => {
    proceedWithBookmark.value = false;

    // Fresh query at click time — avoids stale state from multi-window scenarios
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const clickedTab = tabs[0];
    if (!clickedTab?.url) {
        handleError('No active tab URL found');
        return;
    }
    active_tab.value = clickedTab;   // sync stored state with reality
    // ... rest of handleBookmark unchanged ...
}
```

- [x] In `handleBookmark()`: query current active tab fresh at click time; update `active_tab` before proceeding
- [ ] Test: two Chrome windows — Window A with X.com, Window B with any page. Side panel open in Window B. Switch to Window A → "Analyze This Page" should analyze X.com, not Window B's page.

**Test gate**: Reproduce the original scenario: two windows, switch from Window B to Window A. Verify
backend log shows the correct URL from Window A.

---

### Phase 1.B Complete Checklist ✅
- [ ] Open a WSJ article: analysis completes, then stays visible after `?mod=...` appended to URL
- [ ] Backend logs show exactly 1 `/bookmarks/find` request per page load
- [ ] Switch tabs rapidly between 3 tabs: each tab shows its own content (no leakage)
- [ ] Analyze a slow-loading page, switch tabs mid-analysis: destination tab shows its own (empty) state
- [ ] "Saving document ID for URL:" log always shows the full article URL

---

## Phase 2 — Code Quality & Cleanup
*Goal: Remove dead code, fix deprecated patterns, make the codebase leaner.*

### 2.1 Remove Deprecated Embedding Methods ✅
**File**: `backend/app/services/embedding_service.py`

- [x] Audited callers — only `batch_update_embeddings()` called the deprecated `update_document_embedding()`
- [x] Migrated `batch_update_embeddings()` to call `generate_and_store_document_embeddings()` directly (passes `document` object, not ID)
- [x] Deleted `update_document_embedding()`, `search_similar_documents()`, `find_duplicate_documents()`
- [x] Removed orphaned `Tuple` from the `typing` import

**Test gate**: `grep -r "update_document_embedding\|search_similar_documents\|find_duplicate_documents" backend/` returns no hits.

---

### 2.2 Decouple `db_session` from `research_graph.py` ✅
**File**: `backend/app/chat_workflows/research_graph.py`

- [x] Added `fetch_graph_prompts(db_session) -> GraphPrompts` async function — fetches all 3 prompts, raises on missing
- [x] Changed `build_research_graph(checkpointer, retrieve_tool, prompts)` — removed `db_session` param, added `prompts` dict, raises `ValueError` if prompts are absent
- [x] Moved `PromptService` / `PromptType` to module-level imports in `research_graph.py`
- [x] In `chat_agent_service.get_stream()`: calls `fetch_graph_prompts` and `get_checkpointer` concurrently via `asyncio.gather`, passes `prompts=` to builder
- [x] Added `import asyncio` to `chat_agent_service.py`

**Test gate**: `test_research_agent.py` can be run with mock prompts dict — no live DB needed.

---

### Phase 2 Complete Checklist
- [ ] `mypy backend/app/` passes (or improves from baseline)
- [ ] No `DeprecationWarning` lines in backend logs during normal operation

---

## Phase 3 — Unified Chat UI
*Goal: Web app and Chrome extension chat feel identical.*

### 3.1 Shared CSS Design Tokens — DEFERRED
**Reason**: Web app uses PrimeVue v5 CSS variables (`--p-surface-card`, `--p-primary-500`) while
the extension uses PrimeVue v4 variables (`--surface-card`, `--primary-color`). A single shared CSS
file would break one or both. Both already use `Roboto Mono` ✅. Full token unification requires
upgrading the extension to PrimeVue v5 first (separate effort).

---

### 3.2 Standardize Message Status Model ✅
**Problem**: Extension used `message.streaming` for status text; web used `message.pending`. On tab switch the `streaming` flag caused stale status text to linger.

**Fix applied** (`ChatInterface.vue`):
- `pending=true` is now kept for the full message lifetime (initial wait + all streaming) — matching the web app's semantic
- Spinner shows only when `pending && !content` (not while content is arriving mid-stream)
- Status text condition changed from `message.streaming` to `message.pending`
- Removed all `message.streaming` flag reads and writes

- [x] Removed `streaming` flag from extension message model
- [x] `pending=true` covers full response lifecycle in extension
- [x] Status text condition aligned with web app (`message.pending`)

---

### 3.3 Add Resources/Actions to Extension Chat ✅
**File**: `chrome-extension/src/components/ChatInterface.vue`

- [x] Ported `action-buttons` template block from `ChatPanel.vue`
- [x] Ported `resources-section` template block from `ChatPanel.vue`
- [x] Added `handleActionClick(action)` — sets `inputMessage` to action label and calls `sendMessage()`
- [x] Added corresponding CSS using extension's PrimeVue v4 variables

---

### 3.4 Migrate Extension `ChatInterface.vue` to TypeScript — DEFERRED
**Reason**: Low-value refactor at this stage; extension build doesn't enforce TypeScript. Will revisit after PrimeVue v5 upgrade.

---

### Phase 3 Complete Checklist
- [ ] Side-by-side screenshot comparison of web app chat and extension chat shows identical design
- [ ] Send a message in both interfaces; status indicators behave identically

---

## Phase 4 — Social Comment Writing Feature ✅
*Goal: Agent can draft social media comments using the document content + knowledge base.*

### 4.1 Add `fetch_social_post_tool` ✅
**File**: `backend/app/chat_workflows/tools.py`

- [x] Created `create_fetch_social_post_tool()` using `httpx` + `BeautifulSoup`
- [x] Detects platform from URL (Twitter/X, LinkedIn, Reddit, Facebook, Web)
- [x] Extracts OG metadata (title, description, site_name) + main text content
- [x] Returns structured string: Platform, URL, Site, Title, Description, Content Excerpt
- [x] Moved `BeautifulSoup` import to module level (cleanup)

---

### 4.2 Add `CHAT_SOCIAL_WRITER` Prompt Type ✅
**File**: `backend/app/services/prompt_utils.py`

- [x] Added `CHAT_SOCIAL_WRITER = "Chat Agent: Social Writer"` to `PromptType` enum
- [x] Created `backend/scripts/seed_social_writer_prompt.py` — upserts the prompt in DB
- [x] Prompt instructs agent to use `Document Content` from CURRENT CONTEXT directly;
      falls back to `fetch_social_post_tool` only if content is absent

---

### 4.3 Wire Social Writing into the Research Graph ✅
**File**: `backend/app/chat_workflows/research_graph.py`

- [x] Added `is_social_writing: bool` to `AgentState` and `IntentClassification` TypedDicts
- [x] `intent_node` returns `is_social_writing` from LLM classifier result
- [x] Refactored to conditional routing: `route_to_generate(state)` shared function used across 4 edges
- [x] Extracted shared `_run_generate(state, system_msg, run_name)` helper
- [x] Added `generate_node` (normal Q&A) and `social_generate_node` (social writing) as separate nodes
- [x] `fetch_social_post_tool` wired into `build_research_graph` tools list (was dead code bug — fixed)
- [x] `_SOCIAL_WRITER_FALLBACK` prompt with explicit instruction to use CURRENT CONTEXT content
- [x] `fetch_graph_prompts()` fetches `CHAT_SOCIAL_WRITER` optionally (no error if missing)
- [x] Fixed `tools → generate_node` edge: now routes via `route_to_generate` (was hardcoded)

---

### 4.4 Inject Full Document Content into Agent Context ✅
**File**: `backend/app/services/chat_agent_service.py`

- [x] Removed dead `tools` list (~30 lines) and unused imports from `chat_agent_service.py`
- [x] CURRENT CONTEXT SystemMessage now includes `ai_markdown_content` under `Document Content:`
      so agent has full post text without needing a tool call
- [x] Context order: Title → URL → Summary → Document Content

---

### 4.5 UI — Write Comment Quick-Action Button ✅
**Files**: `frontend/src/components/knowledge_explorer/ChatPanel.vue`,
           `chrome-extension/src/components/ChatInterface.vue`

- [x] Added "Write Comment" button in `quick-actions-row` above the input field in both UIs
- [x] Click pre-fills input with `"Write a comment on this post: "`
- [x] CSS: `.quick-actions-row`, `.quick-action-btn`, `.input-row` added to both files

---

### Phase 4 Complete Checklist
- [x] Intent classifier correctly detects social writing intent (`is_social_writing: true`)
- [x] `social_generate_node` is routed to when social writing is detected
- [x] Agent uses document content from CURRENT CONTEXT (not a tool call) for comments
- [x] 3 comment options (Engaging / Insightful / Conversational) returned
- [ ] Comment drafts rendered in separate copyable cards with Copy button (deferred to Phase 6 UI work)
- [ ] Social comment references current world events for time-sensitive posts (Phase 6)

---

## Phase 5 — Knowledge Graph Enhancement
*Goal: Entity relationships are meaningful and the agent can traverse them.*

### 5.1 Add `EntityRelationship` Table ✅
**File**: `backend/app/models.py`, `backend/migrations/`

- [x] Define `EntityRelationship(id, from_entity_id, to_entity_id, relationship_type, source_document_id, created_at)`
- [x] Created Alembic migration `0e3c95d9a1e4_add_entity_relationships.py`
- [x] Applied — migration is in chain leading to current head `17da34c28575`

---

### 5.2 Extract Entity Relationships During Document Ingestion ✅
**File**: `backend/app/services/dspy_entity_service.py`

- [x] DSPy signature `ExtractEntityRelationships` with entity_names + content_text inputs
- [x] Output: `EntityRelationshipResult` with list of `{from_entity, to_entity, relationship_type}`
- [x] Called in `bookmarks.py` after entity extraction → stored via `adapter.process_document_relationships()`

---

### 5.3 Add `knowledge_graph_tool` to LangGraph Agent ✅
**File**: `backend/app/chat_workflows/tools.py`

- [x] `create_knowledge_graph_tool(user_id, db_session)` — name lookup + relationship traversal
- [x] Returns markdown: entities with descriptions + directed relationship list
- [x] Wired into `chat_agent_service.py` (line 245) and passed to `build_research_graph` via `kg_tool`

---

### 5.4 Improve Knowledge Explorer UI ✅
**File**: `frontend/src/views/library/KnowledgeExplorer.vue`

- [x] "Explore in Chat" button opens scoped chat session
- [x] Backend: `GET /api/v1/knowledge/entity/{id}/relationships` in `knowledge.py` + `KnowledgeService.get_entity_relationships()`
- [x] Frontend: when single entity selected, auto-fetches relationships and shows entity panel
- [x] Relationship type labels rendered as `Tag` chips: `from_entity → [type] → to_entity`

---

### Phase 5 Complete Checklist
- [ ] `SELECT count(*) FROM entity_relationship` > 0 after processing 5 documents
- [ ] Agent query "What is [entity X]'s relationship to [entity Y]?" returns a grounded answer

---

## Phase 6 — Social Comment Writing: Quality Improvements
*Goal: Comments are grounded in real-world current events and rendered with a better UI.*

### 6.1 Add `world_context_tool` — Broader Current-Events Context ✅
**Motivation** (observed 2026-03-02): Comment drafts are accurate to the post content but miss
broader real-world context. Example: a Purim post about "a people at war" produces generic
resilience comments, but omits the active Israel-Iran conflict — which is what gives the post
its urgency and would make a much stronger, more specific comment.

**Design**:
- Tool name: `world_context_tool`
- Input: `topic` (str) — topic extracted from the post (e.g. "Israel Iran war", "Purim 2026")
- Implementation: targeted Google Search with `"{topic} latest news"` via `asyncio.to_thread`
- Return: formatted results with titles, URLs, snippets for top 3–5 results
- Returns `None` (tool excluded) when Google Search credentials are not configured

**Files**:
- `backend/app/chat_workflows/tools.py` — `create_world_context_tool()`
- `backend/app/chat_workflows/research_graph.py` — add to tools list
- `backend/scripts/seed_social_writer_prompt.py` — update prompt with world-context instruction

- [x] Added `create_world_context_tool()` to `tools.py` (wraps `GoogleSearchAPIWrapper`, async via `asyncio.to_thread`)
- [x] Wired into `build_research_graph` tools list alongside `fetch_social_post_tool`
- [x] Updated `_SOCIAL_WRITER_FALLBACK` in `research_graph.py` with CURRENT EVENTS ENRICHMENT section
- [x] Updated DB seed prompt in `seed_social_writer_prompt.py` with matching world-context instruction
- [ ] Run `cd backend && .venv/bin/python scripts/seed_social_writer_prompt.py` to update DB prompt
- [ ] Test: Purim post → comments reference Israel-Iran conflict without user mentioning it

---

### 6.2 UI — Render Comment Drafts as Copyable Cards
**Files**: `frontend/src/components/knowledge_explorer/ChatPanel.vue`,
           `chrome-extension/src/components/ChatInterface.vue`

- [ ] Detect when an AI response contains `Option A`, `Option B`, `Option C` pattern
- [ ] Render each option in a separate card with a "Copy" button
- [ ] Copy button copies just that option's text to clipboard

---

### Phase 6 Complete Checklist
- [ ] Social comment on a geopolitically relevant post references current world events
- [ ] Comment drafts render in separate copyable cards in both web and extension

---

## Phase 7 — Database & Data Model Cleanup ✅
*Goal: Remove legacy fields and stale data. Shrink the schema to what the app actually uses.*

---

### 7.1 Purge Documents Without `ai_markdown_content` ✅

- [x] `backend/scripts/purge_legacy_documents.py` written with dry-run + `--execute` flag
- [ ] Run dry-run: `cd backend && .venv/bin/python scripts/purge_legacy_documents.py`
- [ ] Run with `--execute` after confirming count

---

### 7.2 Remove Legacy DB Columns ✅

Five columns (`source_text_in_html`, `update_at`, `llm_service_meta`, `types_and_concepts`, `cosine_similarity`) dropped.

- [x] 5 fields already absent from `Document` SQLModel in `models.py`
- [x] Migration `17da34c28575_remove_legacy_document_columns.py` applied — `alembic current = head`

---

### 7.3 Remove Dead Code from `Document` Model ✅

- [x] `to_source_text()`, `generate_summary_vector()`, `to_embeddings()` — not present in current `models.py`

---

### 7.4 Fix Web App References to Legacy Fields ✅

- [x] `Documents.vue` — uses `updated_at`; legacy `ai_bullet_points` block absent
- [x] `CollectionDetails.vue` — `cosine_similarity` display already removed
- [x] `DocModel.ts` — clean (no legacy properties)
- [x] `AskQuestionAnswerModel.ts` — clean (no `llm_service_meta`)
- [x] `Bookmark.ts` — clean (no `update_at`)

---

### 7.5 Fix iOS App References to Legacy Fields ✅

Fields were broader than initially mapped — `aiSummary` and `aiBulletPoints` existed in the CoreData model and were referenced in 4 service files.

- [x] `ArticleData.swift` — already clean (uses `aiMarkdownContent`); `aiSummary`/`aiBulletPoints` never in struct
- [x] `iCognition.xcdatamodel` — created version 2 model without `aiBulletPoints` and `aiSummary` attributes
- [x] `CoreDataStack.swift` — added `NSMigratePersistentStoresAutomaticallyOption` + `NSInferMappingModelAutomaticallyOption` for lightweight migration
- [x] `SharedDataManager.swift` — removed `aiSummary`/`aiBulletPoints` from `articleToArticleData()` and `updateArticle()`
- [x] `ContentProcessor.swift` — removed from `convertToArticleData()`
- [x] `CoreDataMigrationService.swift` — removed from `updateArticle()`
- [x] `BackendSyncService.swift` — removed from `convertToArticleData()`

---

### Phase 7 Complete Checklist
- [ ] `SELECT COUNT(*) FROM document WHERE ai_markdown_content IS NULL OR TRIM(ai_markdown_content) = ''` = 0
- [ ] `\d document` in psql shows no legacy columns
- [ ] `grep -r "ai_bullet_points\|source_text_in_html\|llm_service_meta\|types_and_concepts\|cosine_similarity\|update_at" backend/app/` (excluding `legacy_files/`) returns no hits
- [ ] Backend starts cleanly with no SQLAlchemy warnings about missing columns
- [ ] Web app `Documents.vue` date column shows correct date (from `updated_at`)
- [ ] Web app document expansion panel has no blank "Key Points" section
- [ ] iOS app builds successfully after model cleanup

---

## Phase 8 — Unified Chat Hub
*Goal: One chat experience replaces three. Sessions are context-aware, auto-named, and enriched with document retrieval + current-events search.*

### Background

The app currently has three separate chat surfaces:
- **My Library** — `ChatPanel.vue` embedded in a `Splitter` inside `DocumentContainer.vue`
- **Learning Q&A** — full-page chat using the third-party `vue-advanced-chat` web component
- **Knowledge Explorer** — `ChatPanel.vue` inside `KnowledgeExplorer.vue` with its own tab store

All three share the same backend (`chat_agent_service.py` + LangGraph) and the same `ChatPanel.vue` component. The divergence is pure UI overhead. **Option A**: consolidate into one hub at `/chat` (repurposing Learning Q&A), remove chat from the other two pages, and make context (document / entity) flow in as optional session scope.

---

### 8.1 — Native Session Sidebar Component
**New file**: `frontend/src/components/chat/ChatSessionList.vue`

Replace the third-party `vue-advanced-chat` sidebar with an in-house component that renders the session list from `chat_store`.

- [ ] Create `ChatSessionList.vue` with props: `sessions`, `activeSessionId`
- [ ] Each row shows: session title (truncated), scope badge (`📄` / `🏷️` / `🌐`), delete button
- [ ] Emit `select(sessionId)` and `delete(sessionId)` events
- [ ] "New Chat" button at top emits `create`
- [ ] Style with PrimeVue tokens (matches `ChatPanel.vue`)

---

### 8.2 — Unified Chat View
**File**: `frontend/src/views/library/LearningQA.vue` (rewrite in-place)

Rewrite `LearningQA.vue` as the single chat hub. Remove `vue-advanced-chat` dependency.

Layout: `[ChatSessionList | ChatPanel]` side by side (fixed left sidebar, growing right panel).

- [ ] Replace `vue-advanced-chat` template with `ChatSessionList` + `ChatPanel` side by side
- [ ] Wire `ChatSessionList` events to `chat_store`: `select` → `switchActiveSession`, `create` → `createSession`, `delete` → `deleteSession`
- [ ] Pass `activeSession.scope_id` and `activeSession.scope_type` as props to `ChatPanel`
- [ ] Accept optional route query params `?document_id=X` or `?entity_id=Y`:
  - On mount, if param present, call `chat_store.createSession()` with that scope and navigate without the param
- [ ] Remove `vue-advanced-chat` from `package.json` after migration

---

### 8.3 — Remove Chat Panel from My Library
**File**: `frontend/src/views/DocumentContainer.vue`

- [ ] Remove the right `SplitterPanel` (chat section with `Tabs` / `ChatPanel`)
- [ ] Remove unused imports: `Tabs`, `TabList`, `Tab`, `TabPanels`, `TabPanel`, `ChatPanel`, `useChatStore`
- [ ] Remove `chatTabs`, `activeChatTabId`, `addChatTab`, `setActiveChatTab`, `ensureActiveChatTab` logic
- [ ] The content splitter becomes a single panel (table fills full width)
- [ ] Add "💬 Chat" button to `LibraryToolbar` that navigates to `/chat?document_id=X` when a document row is selected/expanded

---

### 8.4 — Repurpose Knowledge Explorer (Entity Browser Only)
**File**: `frontend/src/views/library/KnowledgeExplorer.vue`

- [ ] Remove `ChatPanel` import and template usage
- [ ] Remove tab management (`tab-header`, `tab-buttons`, `handleAddTab`) — the explorer becomes a single-pane entity browser
- [ ] Keep the `FilterTree` entity browser
- [ ] Add "💬 Explore in Chat" button that navigates to `/chat?entity_id=X` when an entity is selected in the tree
- [ ] Clean up `knowledgeExplorerStore.ts`: remove chat tab state (`chatTabs`, `activeChatTabId`, `addChatTab`, `setActiveChatTab`, `ensureActiveChatTab`)

---

### 8.5 — Auto-Name Sessions from First Message
**Backend**: `backend/app/services/chat_agent_service.py` or chat routes

Sessions created as "New Chat" should rename themselves once the user sends their first message.

- [ ] In the `sendMessage` flow: after storing the first user message, if `session.title` is `"New Chat"` or `"Default Chat"`, update it to the first 60 characters of the user message (trimmed, no newlines)
- [ ] Ensure `PATCH /chat/sessions/{id}` endpoint exists and accepts `{ title: string }`
- [ ] **Frontend** (`chat_store.ts`): after `sendMessage()`, if `activeSession.title` is a default name, call the patch endpoint and update `sessions` in state

---

### 8.6 — Add `world_context_tool` to All Chat Sessions
**Files**: `backend/app/chat_workflows/tools.py`, `backend/app/chat_workflows/research_graph.py`

Previously scoped only to social writing (Phase 6.1). Now available in all sessions so the agent can enrich any answer with current events.

- [ ] Implement `create_world_context_tool()` in `tools.py` — wraps `GoogleSearchAPIWrapper` with a news-scoped query: `"{topic} latest news"`
- [ ] Add to `build_research_graph` tools list alongside `retrieve_tool` and `kg_tool` (not gated behind `is_social_writing`)
- [ ] Update the default chat system prompt to hint: *"If the user asks about current events or recent news, use `world_context_tool` to fetch up-to-date information."*
- [ ] Test: ask "What's happening with X right now?" — agent should call `world_context_tool`

---

### 8.7 — Session Scope Badge (Frontend Polish)
**File**: `frontend/src/components/chat/ChatSessionList.vue`

`chat_store.sessions` already carries `scope_type` and `scope_id`. Surface this visually.

- [ ] `scope_type == "document"` → show `📄` badge; look up document title from `library_store.documents` by `scope_id`
- [ ] `scope_type == "entity"` → show `🏷️` badge; use entity name if available
- [ ] No scope → show `🌐` badge (global knowledge base)
- [ ] Badge appears inline next to session title in `ChatSessionList`

---

### Phase 8 Complete Checklist
- [ ] `/chat` route renders unified chat hub (session list + chat panel, no `vue-advanced-chat`)
- [ ] My Library page has no chat panel; selecting a document row shows a "💬 Chat" button linking to `/chat?document_id=X`
- [ ] Knowledge Explorer has no chat panel; selecting an entity shows "💬 Explore in Chat" linking to `/chat?entity_id=X`
- [ ] New session title auto-updates from "New Chat" after first message
- [ ] Agent answers "What's in the news about X?" using `world_context_tool`
- [ ] Session list shows `📄` / `🏷️` / `🌐` scope badges correctly

---

## Implementation Approach Recommendation

### How to Work Through This

**Cycle**: Code → Manual test → Automated test → Commit → Next task

1. **One task at a time.** Don't start Phase 2 until Phase 1 test gates pass.
2. **Test gates are mandatory.** They are not optional polish — they confirm the change worked.
3. **Commit after each numbered task** (1.1, 1.2, etc.) so you can bisect if something breaks.
4. **Phase 4 (social comments) can start in parallel with Phase 3** since they touch different parts of the codebase (backend vs frontend).

### Tooling To Add Along The Way
- `pytest-asyncio` fixtures for all new async service tests
- `httpx` + `TestClient` for route-level API tests
- Langfuse dashboard — use it to verify prompt cache hits vs misses

### What NOT To Do
- Don't refactor everything at once. The phases are ordered intentionally.
- Don't add a new vector DB or graph DB unless Phase 5 proves PostgreSQL can't handle it.
- Don't replace LangGraph — extend it.

---

## Status Legend
- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[!]` Blocked — needs investigation

*Last updated: 2026-03-03*
