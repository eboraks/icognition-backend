"""
End-to-end tests for the chat SSE endpoint after the Agent_Architecture_May_24
refactor. These tests hit a running server and verify the streaming + skill
routing contract.

The user is expected to run the server separately. Tests skip cleanly if the
server isn't reachable.

Run:
    uv run pytest tests/test_chat_stream_endpoint.py -v -s

Env vars:
    ICOG_API_BASE   default: http://localhost:8000
    ICOG_AUTH_TOKEN Firebase ID token (omit when the server runs with DISABLE_AUTH=true)

SSE protocol (post-Agent_Architecture_May_24):
    event: token          — delta to append
    event: content        — full-text replacement (research path one-shot)
    event: draft_replace  — clear buffer; reflection rejected the draft
    event: status         — UI hint
    event: done           — terminal event with {entity_ids, document_ids}
    event: error          — failure

What's covered:
    test_two_turn_no_answer_leak           — regression for the bug that motivated this refactor:
                                             turn 2's response must not be prefixed by turn 1's.
    test_qa_default_skill_no_draft_replace — `qa` has reflect:false → no draft_replace event.
    test_summary_skill_reflection_enabled  — `/summary` runs reflection; answer streams via `token` events.
    test_skill_override_via_query_param    — ?skill=email_draft actually changes routing.
    test_done_event_carries_context        — every successful stream terminates with a `done` event
                                             carrying {entity_ids, document_ids} lists.

These are integration tests — they cost real LLM tokens. Keep them small.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional

import httpx
import pytest

API_BASE = os.getenv("ICOG_API_BASE", "http://localhost:8000")
AUTH_TOKEN = os.getenv("ICOG_AUTH_TOKEN", "")
STREAM_TIMEOUT_S = float(os.getenv("ICOG_STREAM_TIMEOUT", "90"))


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return headers


async def _server_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{API_BASE}/health")
            return r.status_code == 200
    except Exception:
        return False


@dataclass
class SSEEvent:
    event: str
    data: dict


@dataclass
class StreamResult:
    """All events collected from one SSE stream call (post-protocol-cleanup)."""
    events: List[SSEEvent] = field(default_factory=list)

    @property
    def tokens(self) -> List[str]:
        """Deltas from `token` events; concatenated = streamed answer."""
        return [e.data.get("content", "") for e in self.events if e.event == "token"]

    @property
    def streamed_text(self) -> str:
        """
        Frontend-equivalent reconstruction:
          - `token`         → append to buffer
          - `content`       → replace buffer (research one-shot)
          - `draft_replace` → clear buffer
        """
        buf = ""
        for e in self.events:
            if e.event == "token":
                buf += e.data.get("content", "") or ""
            elif e.event == "content":
                buf = e.data.get("content", "") or ""
            elif e.event == "draft_replace":
                buf = ""
        return buf

    @property
    def done(self) -> Optional[dict]:
        """The terminal `done` event carries {entity_ids, document_ids}."""
        for e in reversed(self.events):
            if e.event == "done":
                return e.data
        return None

    @property
    def event_types(self) -> List[str]:
        return [e.event for e in self.events]

    @property
    def errors(self) -> List[str]:
        return [
            e.data.get("content", "") or ""
            for e in self.events
            if e.event == "error"
        ]


async def _create_session(client: httpx.AsyncClient, title: str) -> int:
    r = await client.post(
        f"{API_BASE}/api/v1/chat/sessions",
        json={"title": title, "scope_type": "all_library", "scope_id": None},
        headers=_auth_headers(),
    )
    r.raise_for_status()
    body = r.json()
    return int(body["id"])


async def _delete_session(client: httpx.AsyncClient, session_id: int) -> None:
    try:
        await client.delete(
            f"{API_BASE}/api/v1/chat/sessions/{session_id}",
            headers=_auth_headers(),
        )
    except Exception:
        pass  # best-effort cleanup


async def _send_user_message(client: httpx.AsyncClient, session_id: int, content: str) -> int:
    r = await client.post(
        f"{API_BASE}/api/v1/chat/sessions/{session_id}/messages",
        json={"content": content},
        headers=_auth_headers(),
    )
    r.raise_for_status()
    body = r.json()
    return int(body["id"])


async def _stream(
    client: httpx.AsyncClient,
    session_id: int,
    message_id: int,
    skill: Optional[str] = None,
) -> StreamResult:
    """
    Open the SSE stream and collect every event until end_stream or error.
    Returns a StreamResult so individual tests can assert on what they care about.
    """
    params: Dict[str, str] = {"message_id": str(message_id)}
    if skill:
        params["skill"] = skill

    result = StreamResult()
    url = f"{API_BASE}/api/v1/chat/sessions/{session_id}/stream"

    # `Accept: text/event-stream` is conventional but the route doesn't enforce it.
    async with client.stream(
        "GET",
        url,
        params=params,
        headers={**_auth_headers(), "Accept": "text/event-stream"},
        timeout=STREAM_TIMEOUT_S,
    ) as resp:
        if resp.status_code != 200:
            body = await resp.aread()
            raise AssertionError(
                f"Stream returned {resp.status_code}: {body!r}"
            )

        # Parse SSE: blocks separated by blank lines; each block has `event:` and `data:` lines.
        event_name = ""
        data_buf: List[str] = []
        async for raw_line in resp.aiter_lines():
            if raw_line == "":
                if event_name and data_buf:
                    payload_raw = "\n".join(data_buf)
                    try:
                        payload = json.loads(payload_raw)
                    except json.JSONDecodeError:
                        payload = {"_raw": payload_raw}
                    result.events.append(SSEEvent(event=event_name, data=payload))
                    if event_name in ("done", "error"):
                        return result
                event_name = ""
                data_buf = []
                continue
            if raw_line.startswith(":"):
                continue  # SSE comment
            if raw_line.startswith("event:"):
                event_name = raw_line[len("event:"):].strip()
            elif raw_line.startswith("data:"):
                data_buf.append(raw_line[len("data:"):].lstrip())
            # other fields (id:, retry:) ignored

    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _check_server():
    if not await _server_reachable():
        pytest.skip(
            f"Server at {API_BASE} not reachable. Start it with:\n"
            f"  cd backend && uv run uvicorn app.main:app --reload\n"
            f"and (for these tests) set DISABLE_AUTH=true or export ICOG_AUTH_TOKEN."
        )


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    # Long timeout because /research can take ~30s end-to-end.
    async with httpx.AsyncClient(timeout=STREAM_TIMEOUT_S) as client:
        yield client


@pytest.fixture
async def fresh_session(http_client: httpx.AsyncClient) -> AsyncIterator[int]:
    title = f"pytest-{uuid.uuid4().hex[:8]}"
    sid = await _create_session(http_client, title)
    try:
        yield sid
    finally:
        await _delete_session(http_client, sid)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_two_turn_no_answer_leak(http_client: httpx.AsyncClient, fresh_session: int):
    """
    Regression test for the bug that motivated the refactor.

    Before the fix, turn 2's response was a concatenation of turn-1's answer
    followed by turn-2's answer (the streaming layer was reading a stale
    is_satisfactory=True from the checkpointed state and emitting the prior
    turn's AIMessage as a `content` event before turn-2 tokens streamed).

    After the fix, turn 2 should be solely about turn 2's question.
    """
    msg1_id = await _send_user_message(http_client, fresh_session, "What is checkpointing?")
    t0 = time.monotonic()
    r1 = await _stream(http_client, fresh_session, msg1_id)
    a1 = r1.streamed_text.strip()
    assert a1, f"Turn 1 produced no answer. events={r1.event_types} errors={r1.errors}"

    msg2_id = await _send_user_message(http_client, fresh_session, 'What is "work-stealing architecture"?')
    r2 = await _stream(http_client, fresh_session, msg2_id)
    a2 = r2.streamed_text.strip()
    elapsed = time.monotonic() - t0

    assert a2, f"Turn 2 produced no answer. events={r2.event_types} errors={r2.errors}"

    # The bug: a2 used to literally start with a1.
    a1_prefix = a1[:120].lstrip()
    a2_prefix = a2[:200].lstrip()
    assert not a2_prefix.startswith(a1_prefix), (
        "BUG REGRESSED — turn 2's answer starts with turn 1's answer.\n"
        f"turn 1 prefix:\n  {a1_prefix!r}\n"
        f"turn 2 prefix:\n  {a2_prefix!r}"
    )

    # Sanity: turn 2 should actually mention work-stealing or scheduling.
    a2_low = a2.lower()
    assert any(k in a2_low for k in ("work-stealing", "work stealing", "scheduling", "worker")), (
        f"Turn 2 answer doesn't look related to the question. answer={a2[:300]!r}"
    )

    print(f"\n[two_turn] turn1={len(a1)} chars, turn2={len(a2)} chars, total={elapsed:.1f}s")


async def test_qa_default_skill_no_draft_replace(http_client: httpx.AsyncClient, fresh_session: int):
    """
    The `qa` skill has reflect:false, so the graph must NOT route through
    reflect_node, and the SSE stream must NOT contain a draft_replace event.
    """
    msg_id = await _send_user_message(http_client, fresh_session, "Say hello in one short sentence.")
    result = await _stream(http_client, fresh_session, msg_id)

    assert result.streamed_text, (
        f"qa turn produced no answer. events={result.event_types} errors={result.errors}"
    )
    assert "draft_replace" not in result.event_types, (
        "qa is reflect:false but the stream emitted draft_replace (reflection ran). "
        f"events={result.event_types}"
    )


async def test_summary_skill_reflection_enabled(http_client: httpx.AsyncClient, fresh_session: int):
    """
    `/summary` has reflect:true. We don't require draft_replace to fire (the
    first draft may pass reflection), but we do require the answer to be
    non-empty and streamed via tokens (not the research one-shot path).
    """
    msg_id = await _send_user_message(
        http_client,
        fresh_session,
        "Summarize: Work-stealing is a scheduling strategy where idle workers steal tasks from busy ones.",
    )
    result = await _stream(http_client, fresh_session, msg_id, skill="summary")

    answer = result.streamed_text
    assert answer.strip(), f"summary turn produced no answer. events={result.event_types}"
    # token deltas should arrive (i.e. it went through generate_node, not dispatch_research)
    assert len(result.tokens) > 0, (
        "summary should stream tokens through generate_node, but no `token` events were seen."
    )


async def test_skill_override_via_query_param(http_client: httpx.AsyncClient, fresh_session: int):
    """
    ?skill=email_draft should make the agent reach for the email-draft prompt
    even when the user message itself doesn't say "email". We don't validate
    the exact prose, only that an answer comes back and looks email-shaped.
    """
    msg_id = await _send_user_message(
        http_client,
        fresh_session,
        "Tell my colleague the deploy is delayed by a day due to a flaky migration.",
    )
    result = await _stream(http_client, fresh_session, msg_id, skill="email_draft")

    answer = result.streamed_text.lower()
    assert answer.strip(), f"email_draft turn produced no answer. events={result.event_types}"
    # email_draft.prompt_text asks for "Version A" / "Version B" headings + subject line.
    assert any(k in answer for k in ("subject", "version a", "version b", "hi ", "hello ", "dear ")), (
        f"email_draft answer doesn't look email-shaped:\n{answer[:400]!r}"
    )


async def test_done_event_carries_context(http_client: httpx.AsyncClient, fresh_session: int):
    """
    Every successful turn must terminate with a `done` event carrying
    {entity_ids, document_ids} (both are lists; either may be empty).
    """
    msg_id = await _send_user_message(http_client, fresh_session, "Say 'pong'.")
    result = await _stream(http_client, fresh_session, msg_id)

    ctx = result.done
    assert ctx is not None, (
        f"No `done` event in stream. events={result.event_types} errors={result.errors}"
    )
    assert isinstance(ctx.get("entity_ids"), list)
    assert isinstance(ctx.get("document_ids"), list)
    # `done` must be the LAST event before the stream closes (sanity).
    assert result.event_types[-1] == "done", (
        f"`done` should be the terminal event, got: {result.event_types[-5:]}"
    )
