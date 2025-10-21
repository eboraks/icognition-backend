# System Endpoints for Data Population

This document describes the system endpoints created for populating missing data after code fixes or updates.

## Overview

The system endpoints provide functionality to:
- Find documents that are missing entities, embeddings, or content processing
- Trigger background processing to generate missing data
- Monitor processing statistics

## Endpoints

### 1. Health Check
**GET** `/system/health`

Simple health check for the system routes.

**Response:**
```json
{
  "status": "healthy",
  "service": "system",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### 2. Document Processing Statistics
**GET** `/system/documents/stats`

Get comprehensive statistics about document processing status.

**Response:**
```json
{
  "total_documents": 150,
  "documents_with_entities": 120,
  "documents_with_embeddings": 110,
  "documents_without_entities": 30,
  "documents_without_embeddings": 40,
  "documents_without_both": 20,
  "documents_without_content": 5
}
```

### 3. Find Documents Missing Processing
**GET** `/system/documents/missing-processing`

Find documents that are missing entities, embeddings, or content processing.

**Query Parameters:**
- `missing_entities` (bool, default: true) - Include documents missing entities
- `missing_embeddings` (bool, default: true) - Include documents missing embeddings  
- `missing_content` (bool, default: false) - Include documents missing content processing
- `limit` (int, default: 100, max: 1000) - Maximum number of documents to return

**Response:**
```json
{
  "documents": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "title": "Sample Document",
      "url": "https://example.com/article",
      "created_at": "2024-01-15T10:30:00.000Z",
      "missing": ["entities", "embeddings"],
      "content_length": 2500
    }
  ],
  "total_found": 25,
  "limit": 100,
  "filters": {
    "missing_entities": true,
    "missing_embeddings": true,
    "missing_content": false
  }
}
```

### 4. Trigger Document Processing
**POST** `/system/documents/process`

Trigger background processing for specific documents or all documents missing processing.

**Request Body:**
```json
{
  "document_ids": ["123e4567-e89b-12d3-a456-426614174000"], // Optional: specific documents
  "user_id": "user123", // Optional: filter by user
  "process_entities": true,
  "process_embeddings": true,
  "process_content": true
}
```

**Response:**
```json
{
  "message": "Processing triggered for 5 documents",
  "documents_processed": 5,
  "tasks_triggered": 15,
  "document_ids": ["123e4567-e89b-12d3-a456-426614174000", "..."]
}
```

### 5. Process All Missing Data
**POST** `/system/documents/process-all-missing`

Convenience endpoint to process all documents missing any type of processing.

**Response:**
```json
{
  "message": "Complete processing triggered for 25 documents",
  "documents_processed": 25,
  "tasks_triggered": 75,
  "document_ids": ["123e4567-e89b-12d3-a456-426614174000", "..."]
}
```

## Usage Examples

### 1. Check Current Status
```bash
# Get processing statistics
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8889/system/documents/stats

# Find documents missing processing
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "http://localhost:8889/system/documents/missing-processing?limit=10"
```

### 2. Process Specific Documents
```bash
# Process specific documents
curl -X POST \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"document_ids": ["123e4567-e89b-12d3-a456-426614174000"], "process_entities": true, "process_embeddings": true}' \
     http://localhost:8889/system/documents/process
```

### 3. Process All Missing Data
```bash
# Process all documents missing any processing
curl -X POST \
     -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8889/system/documents/process-all-missing
```

### 4. Using the Test Script
```bash
# Run all tests
python test_system_endpoints.py --base-url http://localhost:8889 --auth-token YOUR_TOKEN

# Test specific endpoint
python test_system_endpoints.py --test stats --auth-token YOUR_TOKEN

# Test without authentication (if DISABLE_AUTH is enabled)
python test_system_endpoints.py --test all
```

## Background Processing

The endpoints trigger the following background tasks:

1. **Content Processing** (`_process_document_content`)
   - Generates AI summaries and bullet points
   - Updates document with `ai_is_about` and `ai_bullet_points`

2. **Entity Extraction** (`_process_document_entities`)
   - Extracts entities from document content using Gemini AI
   - Creates entity records and document-entity relationships

3. **Embedding Generation** (`_process_document_embeddings`)
   - Generates vector embeddings for document content
   - Enables semantic search functionality

## Authentication

All endpoints require Firebase authentication unless `DISABLE_AUTH` is enabled in the configuration.

## Rate Limiting

The endpoints respect the same rate limiting as other API endpoints. Processing large numbers of documents may take time due to background task processing.

## Monitoring

Use the statistics endpoint to monitor processing progress:
```bash
# Check progress
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8889/system/documents/stats
```

## Error Handling

All endpoints return appropriate HTTP status codes:
- `200` - Success
- `401` - Authentication required
- `403` - Access forbidden
- `404` - Resource not found
- `500` - Internal server error

Error responses include detailed error messages:
```json
{
  "detail": "Failed to trigger processing: Database connection error"
}
```

## Best Practices

1. **Start Small**: Test with a few documents first using specific document IDs
2. **Monitor Progress**: Use the stats endpoint to track processing completion
3. **Batch Processing**: Use reasonable limits (100-200 documents) to avoid overwhelming the system
4. **Check Content**: Ensure documents have sufficient content before processing
5. **Authentication**: Always use proper Firebase authentication tokens

## Troubleshooting

### Common Issues

1. **No Documents Found**: Check if documents have sufficient content (minimum 10 characters)
2. **Processing Fails**: Check background task logs for specific error messages
3. **Authentication Errors**: Verify Firebase token is valid and not expired
4. **Rate Limiting**: Wait between requests if hitting rate limits

### Debug Mode

Enable debug logging to see detailed processing information:
```bash
# Set log level to DEBUG in your environment
export LOG_LEVEL=DEBUG
```
