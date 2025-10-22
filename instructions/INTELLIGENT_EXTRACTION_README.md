# Intelligent HTML Content Extraction with LLM

This document describes the intelligent HTML content extraction system that uses Gemini Flash Lite to extract meaningful content from web pages with fallback to BeautifulSoup.

## Overview

The system uses a **LLM-first approach** to extract content from HTML:
1. **Primary**: Gemini Flash Lite analyzes HTML and extracts structured content
2. **Fallback**: BeautifulSoup extracts text if LLM fails or has low confidence

## Features

### Intelligent Page Type Detection

The LLM can identify and handle different page types:
- **News Articles** - Extracts article text, author, publication date
- **Blog Posts** - Extracts post content and metadata
- **Product Pages** - Extracts product name, description, price, features
- **Documentation** - Extracts main topic and content
- **Social Media** - Extracts post, author, tags, images
- **Forum Posts** - Extracts discussion content
- **Landing Pages** - Identifies and explains why content can't be extracted
- **Wiki Pages** - Extracts article content

### Smart Content Filtering

The LLM automatically excludes noise:
- Navigation menus, sidebars, footers
- Advertisements and promotional content
- Related articles/products lists
- Comments sections (unless forum/social media)
- Cookie notices, popups, banners
- Social media share buttons

### Structured Data Extraction

Extracts structured data based on page type:

**Social Media:**
- Post content
- Author
- Image URLs
- Tags
- Post date

**Product Pages:**
- Product name
- Description
- Price
- Features list

**News/Blog:**
- Article text
- Author
- Publication date
- Tags

## Data Model

### Pydantic Models

**PageType Enum:**
```python
class PageType(str, Enum):
    BLOG_POST = "blog_post"
    NEWS_ARTICLE = "news_article"
    PRODUCT_PAGE = "product_page"
    DOCUMENTATION = "documentation"
    LANDING_PAGE = "landing_page"
    SOCIAL_MEDIA = "social_media"
    FORUM_POST = "forum_post"
    WIKI = "wiki"
    OTHER = "other"
    NOT_CLEAR = "not_clear"
```

**ContentExtraction Model:**
```python
class ContentExtraction(BaseModel):
    page_type: PageType
    title: str
    content: str  # Main extracted content
    author: Optional[str]
    publication_date: Optional[str]
    tags: List[str]
    metadata: Dict[str, Any]
    social_media_data: Optional[SocialMediaPost]
    product_data: Optional[ProductInfo]
    extraction_confidence: float  # 0.0 to 1.0
    extraction_method: str  # "llm" or "beautifulsoup"
    extraction_notes: Optional[str]  # Why content couldn't be extracted
```

### Database Storage

**New Field:** `extracted_content` (JSONB)
- Stores the complete `ContentExtraction` result
- Indexed with GIN for fast JSON queries
- Queryable using PostgreSQL JSON operators

**Example Queries:**
```sql
-- Find news articles
SELECT * FROM document 
WHERE extracted_content->>'page_type' = 'news_article';

-- Find high-confidence extractions
SELECT * FROM document 
WHERE (extracted_content->>'extraction_confidence')::float > 0.8;

-- Find documents with product data
SELECT * FROM document 
WHERE extracted_content->'product_data' IS NOT NULL;

-- Find LLM-extracted documents
SELECT * FROM document 
WHERE extracted_content->>'extraction_method' = 'llm';
```

## Configuration

**Model Configuration:**
- Model: `GEMINI_FLASH_LITE_MODEL` (default: `models/gemini-2.5-flash-lite`)
- Temperature: 0.1 (low for consistent extraction)
- Max Output Tokens: 8192
- Response Format: JSON with Pydantic schema

**Content Limits:**
- Max HTML size: 80,000 characters (~20k tokens)
- Automatically truncates larger HTML

## Confidence Scoring

The LLM assigns confidence scores based on extraction quality:

- **High (0.7-1.0)**: Clear page type, clean content extraction
- **Medium (0.4-0.7)**: Content present but page structure unclear
- **Low (0.0-0.4)**: Extraction failed or no clear content

**Threshold**: Confidence >= 0.5 uses LLM result, otherwise falls back to BeautifulSoup

## Implementation Flow

### 1. HTML Submission
Chrome extension or mobile app sends raw HTML via POST request:
```json
{
  "content": "<html>...</html>",
  "content_type": "html",
  "title": "Page Title",
  "url": "https://example.com/article"
}
```

### 2. LLM Extraction
`DocumentService._extract_content_with_llm()`:
1. Truncates HTML to 80k chars if needed
2. Sends to Gemini Flash Lite with structured output schema
3. Returns `ContentExtraction` object with all metadata

### 3. Content Decision
`DocumentService._extract_text_from_html()`:
- If confidence >= 0.5: Use LLM extraction
- If confidence < 0.5: Fall back to BeautifulSoup
- On any error: Fall back to BeautifulSoup

### 4. Storage
`DocumentService.create_document_from_content()`:
- Stores extracted text in `document.content`
- Stores full extraction metadata in `document.extracted_content` (JSONB)
- Includes page type, confidence, method, structured data

## Usage Examples

### Creating Document with HTML Content

```python
# Via API
POST /documents/
{
  "content": "<html>...</html>",
  "content_type": "html",
  "title": "Article Title"
}

# Response includes:
{
  "id": "...",
  "title": "Article Title",
  "content": "Extracted clean text...",
  "extracted_content": {
    "page_type": "news_article",
    "title": "Article Title",
    "content": "Extracted clean text...",
    "author": "John Doe",
    "publication_date": "2024-10-21",
    "extraction_confidence": 0.95,
    "extraction_method": "llm",
    "tags": ["politics", "technology"]
  }
}
```

### Querying Extracted Data

```python
# SQLAlchemy query for news articles
from sqlalchemy import select
from app.models import Document

query = select(Document).where(
    Document.extracted_content['page_type'].astext == 'news_article'
)

# Filter by confidence
query = select(Document).where(
    Document.extracted_content['extraction_confidence'].cast(Float) > 0.8
)
```

## Fallback Behavior

### When LLM Extraction is Used
- Confidence >= 0.5
- Valid JSON response from Gemini
- No exceptions during processing

### When BeautifulSoup Fallback is Used
- Confidence < 0.5
- LLM returns "not_clear" page type
- JSON parsing fails
- Gemini API errors
- Any unexpected exceptions

### Metadata for Fallback
```json
{
  "extraction_method": "beautifulsoup_fallback",
  "extraction_confidence": 0.0,
  "page_type": "other",
  "error": "LLM extraction failed: timeout"
}
```

## Benefits

### Over Pure BeautifulSoup
- **Smarter extraction**: Understands page structure semantically
- **Filters noise**: Automatically excludes ads, navigation, etc.
- **Page-specific logic**: Different extraction for different page types
- **Structured data**: Extracts product info, social media posts, etc.
- **Better quality**: Focuses on main content, not boilerplate

### With BeautifulSoup Fallback
- **Reliability**: Always extracts something, even if LLM fails
- **No dependency on external API**: Works offline if needed
- **Cost control**: Only uses LLM when beneficial
- **Performance**: Fast fallback for simple pages

## Performance Considerations

### Token Usage
- **Input**: ~20k tokens max (80k chars HTML)
- **Output**: ~2k tokens typical
- **Cost**: Minimal with Flash Lite model

### Processing Time
- **LLM extraction**: 2-5 seconds typical
- **BeautifulSoup**: <100ms
- **Total with LLM**: 2-5 seconds
- **Total with fallback**: <100ms

### Caching
- Gemini service includes 1-hour response cache
- Reduces costs for repeated extractions
- Improves performance for re-processing

## Monitoring

### Logs to Watch
```
INFO - LLM extraction successful: news_article, confidence: 0.95
WARNING - LLM extraction low confidence or failed, falling back to BeautifulSoup
ERROR - Error in LLM extraction, falling back to BeautifulSoup: timeout
```

### Key Metrics
- Extraction method distribution (LLM vs BeautifulSoup)
- Average confidence scores
- Page type distribution
- Fallback rate

### Database Queries
```sql
-- Extraction method distribution
SELECT 
    extracted_content->>'extraction_method' as method,
    COUNT(*) as count
FROM document
WHERE extracted_content IS NOT NULL
GROUP BY method;

-- Average confidence by page type
SELECT 
    extracted_content->>'page_type' as page_type,
    AVG((extracted_content->>'extraction_confidence')::float) as avg_confidence,
    COUNT(*) as count
FROM document
WHERE extracted_content IS NOT NULL
GROUP BY page_type;
```

## Troubleshooting

### Issue: All extractions falling back to BeautifulSoup
**Cause**: Gemini API key not configured or model not available
**Solution**: Check `GOOGLE_API_KEY` in environment and verify `GEMINI_FLASH_LITE_MODEL` is valid

### Issue: Low confidence scores
**Cause**: HTML is heavily obfuscated or JavaScript-rendered
**Solution**: This is expected behavior - BeautifulSoup fallback will handle it

### Issue: Extraction taking too long
**Cause**: Large HTML documents
**Solution**: Already handled - HTML truncated to 80k chars

### Issue: Missing structured data
**Cause**: Page doesn't match expected type or data not available
**Solution**: Check `extraction_notes` in extracted_content for details

## Future Enhancements

Potential improvements:
1. Re-process existing documents with LLM extraction
2. Add extraction quality feedback loop
3. Fine-tune confidence thresholds per page type
4. Add more page types (e.g., academic papers, recipes)
5. Extract additional structured data (authors, citations, etc.)
6. Add extraction analytics dashboard

## Migration

The database migration adds:
- `extracted_content` JSONB column to `document` table
- GIN index on `extracted_content` for fast queries

**Migration ID:** `49654ff5f87a`

**To apply:**
```bash
cd backend
alembic upgrade head
```

**To rollback:**
```bash
alembic downgrade -1
```

