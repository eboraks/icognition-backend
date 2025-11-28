import re
from typing import Optional

from bs4 import BeautifulSoup


def extract_text_from_html(html: Optional[str]) -> str:
    """Convert HTML content into normalized plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)

    lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped and len(stripped) > 1:
            lines.append(stripped)

    cleaned = '\n'.join(lines)
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    return cleaned.strip()

