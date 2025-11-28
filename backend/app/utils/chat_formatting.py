import html
import re
from typing import List


LIST_PREFIXES = ("* ", "- ", "• ")


URL_PATTERN = re.compile(r"(https?://[^\s<]+)")


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
    """Escape HTML and apply simple markdown-style emphasis."""
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

    return _linkify(escaped)


def format_chat_message(content: str) -> str:
    """
    Convert plain text/markdown-like chat content into sanitized HTML that preserves
    paragraphs, bullet lists, and simple emphasis while preventing arbitrary HTML.
    """
    if not content:
        return "<p></p>"

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

