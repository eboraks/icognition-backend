import html
import re
from typing import List


LIST_PREFIXES = ("* ", "- ", "• ")


URL_PATTERN = re.compile(r"(https?://[^\s<]+)")

# Match <source doc_id="123">Title</source> tags from LLM output
SOURCE_TAG_PATTERN = re.compile(
    r'<source\s+doc_id=["\'](\d+)["\']>(.*?)</source>',
    re.DOTALL,
)


def _clean_source_title(raw_title: str) -> str:
    """Clean a source title: collapse whitespace/newlines, truncate if too long."""
    title = re.sub(r'\s+', ' ', raw_title).strip()
    if len(title) > 120:
        title = title[:117] + "..."
    return title


def _build_source_html(doc_id: str, title: str) -> str:
    """Build the interactive source-ref HTML. Output is always a single line."""
    safe_title = html.escape(title, quote=True)
    return (
        f'<span class="source-ref" data-doc-id="{doc_id}">'
        f'"{safe_title}"'
        f'<button class="source-info-btn" data-doc-id="{doc_id}" '
        f'data-doc-title="{safe_title}" title="Explore this source">'
        f'<i class="pi pi-info-circle"></i>'
        f'</button>'
        f'</span>'
    )


def process_source_tags(text: str) -> str:
    """Convert <source doc_id="ID">Title</source> tags and SOURCE_N references
    into interactive HTML with an info button."""

    # 1) Handle <source doc_id="ID">Title</source> tags
    def _replace_source(match: re.Match) -> str:
        doc_id = match.group(1)
        title = _clean_source_title(match.group(2))
        return _build_source_html(doc_id, title)

    text = SOURCE_TAG_PATTERN.sub(_replace_source, text)

    # 2) Handle LLM's alternative formats like (Source: "Title" (doc_id=123))
    def _replace_paren_source(match: re.Match) -> str:
        title = _clean_source_title(match.group(1))
        doc_id = match.group(2)
        return _build_source_html(doc_id, title)

    text = re.sub(
        r'\(Source:\s*"([^"]+?)"\s*\(doc_id=(\d+)\)\)',
        _replace_paren_source,
        text,
    )

    return text


def _linkify(escaped_text: str) -> str:
    """Convert plain URLs into clickable links."""

    def _replace(match: re.Match) -> str:
        url = match.group(0)
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
            f"{url}"
            "</a>"
        )

    return URL_PATTERN.sub(_replace, escaped_text)


def _format_inline(text: str) -> str:
    """Escape HTML and apply simple markdown-style emphasis.
    Preserves pre-processed <span class="source-ref"> blocks from _process_source_tags."""

    # Temporarily replace source-ref spans with placeholders to protect from escaping.
    # Use a format without underscores to avoid triggering markdown bold (__x__).
    source_spans: list[str] = []

    def _stash_source(match: re.Match) -> str:
        idx = len(source_spans)
        source_spans.append(match.group(0))
        return f"\x00SRCREF{idx}\x00"

    text = re.sub(r'<span class="source-ref".*?</span>', _stash_source, text, flags=re.DOTALL)

    escaped = html.escape(text.strip(), quote=True)
    if not escaped:
        return ""

    def replace(pattern: str, repl: str, value: str) -> str:
        return re.sub(pattern, repl, value, flags=re.DOTALL)

    # Apply in order: bold+italic, bold, italic, underscore variants
    escaped = replace(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", escaped)
    escaped = replace(r"___(.+?)___", r"<strong><em>\1</em></strong>", escaped)
    escaped = replace(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = replace(r"__(.+?)__", r"<strong>\1</strong>", escaped)
    escaped = replace(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    escaped = replace(r"_(.+?)_", r"<em>\1</em>", escaped)

    escaped = _linkify(escaped)

    # Restore source spans
    for idx, span_html in enumerate(source_spans):
        escaped = escaped.replace(f"\x00SRCREF{idx}\x00", span_html)

    return escaped


def format_chat_message(content: str) -> str:
    """
    Convert plain text/markdown-like chat content into sanitized HTML that preserves
    paragraphs, bullet lists, and simple emphasis while preventing arbitrary HTML.
    Source tags (<source doc_id="ID">Title</source>) are converted to interactive buttons.
    """
    if not content:
        return "<p></p>"

    # Process <source> tags BEFORE splitting/escaping (they contain raw HTML output)
    content = process_source_tags(content)

    lines = content.splitlines()
    html_parts: List[str] = []
    list_buffer: List[str] = []
    paragraph_buffer: List[str] = []

    def flush_list():
        nonlocal list_buffer
        if list_buffer:
            items = "".join(f"<li>{_format_inline(item)}</li>" for item in list_buffer if item.strip())
            if items:
                html_parts.append(f"<ul>{items}</ul>")
            list_buffer = []

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            paragraph_text = " ".join(paragraph_buffer)
            html_parts.append(f"<p>{_format_inline(paragraph_text)}</p>")
            paragraph_buffer = []

    for raw_line in lines:
        line = raw_line.rstrip()

        if not line.strip():
            flush_list()
            flush_paragraph()
            continue

        stripped = line.lstrip()
        prefix = stripped[:2]

        if any(stripped.startswith(pfx) for pfx in LIST_PREFIXES):
            flush_paragraph()
            # Remove prefix (consider two chars) and keep rest
            list_item = stripped[2:] if prefix in ("* ", "- ", "• ") else stripped[1:]
            list_buffer.append(list_item)
        else:
            flush_list()
            paragraph_buffer.append(line.strip())

    flush_list()
    flush_paragraph()

    if not html_parts:
        return "<p></p>"

    return "".join(html_parts)

