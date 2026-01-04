# To-Do Tasks

## iOS App - Share Extension Metadata Support

### Icon URL Support (Future Enhancement)

**Status**: Pending

**Description**: 
Currently, the iOS Share Extension extracts metadata from LinkPresentation framework including:
- ✅ Title (from og:title)
- ✅ Description (from og:description) 
- ✅ Image URL (from og:image)
- ❌ Icon URL (from site favicon) - **Not yet implemented**

**Current State**:
- LinkPresentation provides icon URL via `metadata.iconProvider`
- Icon URL is extracted in ShareExtensionViewModel but not stored
- Core Data Article model has `metadataDescription` and `metadataImageURL` but no `metadataIconURL`
- Backend Document model has `metadata_description` and `image_url` but no `icon_url`
- Backend Bookmark model has `bookmark_metadata` JSON field that could store icon URL

**Implementation Options**:

1. **Quick Fix (Recommended for MVP)**: Store icon URL in existing metadata JSON fields
   - Store in Bookmark's `bookmark_metadata` JSON
   - Store in Document's `document_metadata` JSON
   - No database migration needed

2. **Dedicated Fields (Better long-term)**: Add dedicated icon URL fields
   - Add `metadataIconURL` to Core Data Article model
   - Add `icon_url` to backend Document model  
   - Add `icon_url` to backend Bookmark model
   - Requires database migration

**Files to Update** (if implementing):
- `iso-app/iso-app/iCognition.xcdatamodeld/iCognition.xcdatamodel/contents` - Add metadataIconURL attribute
- `iso-app/iso-app/Models/ArticleData.swift` - Add iconURL to ArticleMetadata struct
- `iso-app/iso-app/ShareExtension/ShareExtensionViewModel.swift` - Store icon URL when saving
- `iso-app/iso-app/Services/BackendSyncService.swift` - Include icon URL in sync
- `backend/app/models.py` - Add icon_url to Document model (if using dedicated field)
- `backend/app/models.py` - Add icon_url to Bookmark model (if using dedicated field)
- Backend migration script for new fields (if using dedicated fields)

**Priority**: Low - Icon URL is nice-to-have for UI display but not critical for core functionality
