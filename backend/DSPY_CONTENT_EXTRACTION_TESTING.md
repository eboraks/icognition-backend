# DSPy Content Extraction Service - Testing Guide

This guide explains how to test the new DSPy-based content extraction service that combines content analysis and entity extraction into a single unified task.

## Overview

The DSPy extraction service uses Google Gemini models (Flash and Flash Lite) to extract structured content including:
- Title and source type
- Summary
- Key takeaways
- Key entities (organizations, people, topics)
- Content analysis (objectivity, tone, intent)

## Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This will install:
- `dspy-ai>=2.4.0` - DSPy framework for structured AI interactions
- `thefuzz>=0.22.1` - Fuzzy string matching for entity validation

### 2. Verify API Key

Ensure your Google API key is set in the environment or `.env` file:
```bash
export GOOGLE_API_KEY="your-api-key-here"
```

Or add to `.env`:
```
GOOGLE_API_KEY=your-api-key-here
```

### 3. Ensure Database Connection

The test loads existing documents from your database. Make sure:
- Database is running
- Documents exist with content to analyze

## Running Tests

### Option 1: Using the CLI Test Runner (Recommended)

```bash
# Test with specific document IDs
python run_dspy_test.py --ids 1,5,10

# Test with a single document
python run_dspy_test.py --ids 25

# Example with multiple documents
python run_dspy_test.py --ids 1,2,3,4,5
```

### Option 2: Direct Python Execution

```bash
cd backend
python -m pytest tests/test_dspy_extraction.py::main --ids="1,5,10" -v
```

## What Gets Tested

For each document and model combination, the test:

1. **Extracts Content** - Runs DSPy extraction with specified model
2. **Validates Results**:
   - Summary length (100-500 chars)
   - Key takeaways count (3-7 items)
   - Entity count (1-10 entities)
   - Entity accuracy (entities match content using fuzzy matching)
   - Required fields present
   - Type compliance (Literal types validated)
3. **Measures Performance** - Extraction time per document

## Output

### Console Output

```
============================================================
DSPy Content Extraction Test Results
============================================================

Timestamp: 2025-01-26_14-30-45
Total Tests: 6

--- Flash Model ---
  Successful: 3/3
  Failed: 0
  Avg Time: 2.45s
  Avg Pass Rate: 95.50%

--- Flash Lite Model ---
  Successful: 3/3
  Failed: 0
  Avg Time: 1.85s
  Avg Pass Rate: 92.30%

============================================================
```

### JSON Results File

Detailed results are saved to: `tests/data/dspy_extraction_results_YYYY-MM-DD_HH-MM-SS.json`

The file contains:
- Summary statistics for both models
- Per-document extraction results
- Validation details for each check
- Full extracted data (JSON)
- Performance metrics

## Test Files Structure

```
backend/
├── app/services/
│   ├── dspy_models.py                    # Pydantic models for extraction
│   └── dspy_extraction_service.py        # DSPy service implementation
├── tests/
│   ├── test_dspy_extraction.py          # Test suite
│   └── data/
│       ├── .gitkeep
│       └── dspy_extraction_results_*.json # Test results
├── run_dspy_test.py                      # CLI test runner
└── requirements.txt                      # Updated with dspy-ai and thefuzz
```

## Validation Criteria

The test evaluates extraction quality using these criteria:

1. **Summary Quality** (100-500 chars)
2. **Key Takeaways** (3-7 items, each >10 chars)
3. **Entity Accuracy** (entities appear in content, fuzzy match >70%)
4. **Entity Count** (1-10 entities)
5. **Field Completeness** (all required fields populated)
6. **Type Compliance** (Literal types validated)
7. **Performance** (<30s per document acceptable)

## Model Comparison

The test compares two models:

- **Flash** (`gemini-2.0-flash`): Faster, suitable for most content
- **Flash Lite** (`gemini-2.5-flash-lite`): Even faster, lighter weight

Results show:
- Success rates
- Average extraction times
- Validation pass rates
- Performance trade-offs

## Next Steps

After testing:

1. **Review Results** - Check JSON files for detailed extraction quality
2. **Compare Models** - Determine which model works best for your documents
3. **Adjust Validation** - Modify validation criteria if needed
4. **Integration** - Once validated, integrate into production routes

## Troubleshooting

### "Google API key is required"

Make sure `GOOGLE_API_KEY` is set in your environment or `.env` file.

### "Documents not found"

Verify document IDs exist in your database:
```sql
SELECT id, title FROM document WHERE id IN (1,5,10);
```

### Import Errors

Ensure all dependencies are installed:
```bash
pip install dspy-ai thefuzz
```

### Slow Performance

- Check API rate limits
- Verify network connection
- Consider using Flash Lite model for faster results

## Example Usage

```bash
# 1. Get some document IDs from your database
python -c "from app.models import Document; from app.db.database import async_session; import asyncio; asyncio.run(async_session())"

# 2. Run tests on those documents
python run_dspy_test.py --ids 1,2,3

# 3. Check results
cat tests/data/dspy_extraction_results_*.json | jq '.summary'

# 4. Review detailed results for a specific document
cat tests/data/dspy_extraction_results_*.json | jq '.detailed_results[0]'
```

