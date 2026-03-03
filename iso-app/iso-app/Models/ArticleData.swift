//
//  ArticleData.swift
//  iso-app
//
//  Data models for articles and metadata
//

import Foundation

// MARK: - Article Data Model

struct ArticleData: Codable, Identifiable {
    var id: String { url }
    let url: String
    let title: String
    let domain: String
    let content: String?
    let metadata: ArticleMetadata?
    let savedAt: Date
    
    // Backend integration fields
    let backendBookmarkId: String?
    let backendDocumentId: String?
    
    // AI content field (from backend)
    let aiMarkdownContent: String?

    // HTML file storage fields
    let htmlFilePath: String?
    let hasLocalHTML: Bool

    init(url: String, title: String, domain: String, content: String? = nil, metadata: ArticleMetadata? = nil, savedAt: Date = Date(), backendBookmarkId: String? = nil, backendDocumentId: String? = nil, aiMarkdownContent: String? = nil, htmlFilePath: String? = nil, hasLocalHTML: Bool = false) {
        self.url = url
        self.title = title
        self.domain = domain
        self.content = content
        self.metadata = metadata
        self.savedAt = savedAt
        self.backendBookmarkId = backendBookmarkId
        self.backendDocumentId = backendDocumentId
        self.aiMarkdownContent = aiMarkdownContent
        self.htmlFilePath = htmlFilePath
        self.hasLocalHTML = hasLocalHTML
    }
    
    // Custom decoding to handle missing savedAt field and content field
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        self.url = try container.decode(String.self, forKey: .url)
        self.title = try container.decode(String.self, forKey: .title)
        self.domain = try container.decode(String.self, forKey: .domain)
        self.content = try container.decodeIfPresent(String.self, forKey: .content)
        self.metadata = try container.decodeIfPresent(ArticleMetadata.self, forKey: .metadata)
        
        // Handle savedAt field - use current date if missing
        if let savedAt = try container.decodeIfPresent(Date.self, forKey: .savedAt) {
            self.savedAt = savedAt
        } else {
            self.savedAt = Date()
        }
        
        // Handle backend integration fields
        self.backendBookmarkId = try container.decodeIfPresent(String.self, forKey: .backendBookmarkId)
        self.backendDocumentId = try container.decodeIfPresent(String.self, forKey: .backendDocumentId)
        
        // Handle AI content
        self.aiMarkdownContent = try container.decodeIfPresent(String.self, forKey: .aiMarkdownContent)

        // Handle HTML file storage fields
        self.htmlFilePath = try container.decodeIfPresent(String.self, forKey: .htmlFilePath)
        self.hasLocalHTML = try container.decodeIfPresent(Bool.self, forKey: .hasLocalHTML) ?? false
    }

    private enum CodingKeys: String, CodingKey {
        case url, title, domain, content, metadata, savedAt
        case backendBookmarkId, backendDocumentId
        case aiMarkdownContent
        case htmlFilePath, hasLocalHTML
    }
}

// MARK: - Article Metadata

struct ArticleMetadata: Codable {
    let description: String?
    let imageURL: String?
    let author: String?
    let publishedDate: Date?
    
    init(description: String? = nil, imageURL: String? = nil, author: String? = nil, publishedDate: Date? = nil) {
        self.description = description
        self.imageURL = imageURL
        self.author = author
        self.publishedDate = publishedDate
    }
}

// MARK: - Shared Content Item

struct SharedContentItem: Codable, Identifiable {
    let id: String
    let title: String
    let url: URL
    let timestamp: Date
    let metadata: [String: String]
    
    init(title: String, url: URL, metadata: [String: Any] = [:]) {
        self.id = UUID().uuidString
        self.title = title
        self.url = url
        self.timestamp = Date()
        
        // Convert metadata to String dictionary for Codable
        var stringMetadata: [String: String] = [:]
        for (key, value) in metadata {
            if let stringValue = value as? String {
                stringMetadata[key] = stringValue
            } else {
                stringMetadata[key] = String(describing: value)
            }
        }
        self.metadata = stringMetadata
    }
}

// MARK: - Processed Content

struct ProcessedContent {
    let id: String
    let title: String
    let url: URL
    let domain: String
    let timestamp: Date
    let metadata: [String: Any]
    let articleData: ArticleData
}

// MARK: - Content Stats

struct ContentStats {
    let totalArticles: Int
    let recentArticles: Int
    let uniqueDomains: Int
    let lastUpdate: Date?
}

// MARK: - Domain Stats

struct DomainStats {
    let domain: String
    let count: Int
}

// MARK: - Processing Status

struct ProcessingStatus {
    let isProcessing: Bool
    let processedCount: Int
    let lastProcessedAt: Date?
}

struct ProcessingStats {
    let isProcessing: Bool
    let processedCount: Int
    let lastProcessedAt: Date?
}

// MARK: - Document Data (from Backend)

/// Document data from the backend API
struct DocumentData: Codable {
    let id: Int  // Changed from String to Int to match backend
    let title: String?
    let url: String?
    let content: String?
    let aiIsAbout: String?
    let aiMarkdownContent: String?
    let updatedAt: String?
    let userId: String?
    let contentSource: String?
    let author: String?
    let publicationDate: String?
    let description: String?
    let keywords: String?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case url
        case content
        case aiIsAbout = "ai_is_about"
        case aiMarkdownContent = "ai_markdown_content"
        case updatedAt = "updated_at"
        case userId = "user_id"
        case contentSource = "content_source"
        case author
        case publicationDate = "publication_date"
        case description
        case keywords
    }
}

// MARK: - Backend Bookmark Data

struct BookmarkData: Decodable {
    let id: Int
    let documentId: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case documentId = "document_id"
    }
}

struct BackendBookmarkCreateRequest: Encodable {
    let url: String
    let title: String
    let description: String?
    let content: String?
    let metadata: [String: AnyCodable]?
}

// Helper for encoding Any to JSON
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "AnyCodable cannot decode value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let string = value as? String {
            try container.encode(string)
        } else if let int = value as? Int {
            try container.encode(int)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let bool = value as? Bool {
            try container.encode(bool)
        } else if let date = value as? Date {
            // Handle Date encoding properly
            let formatter = ISO8601DateFormatter()
            try container.encode(formatter.string(from: date))
        } else if let dict = value as? [String: Any] {
            let anyCodableDict = dict.mapValues { AnyCodable($0) }
            try container.encode(anyCodableDict)
        } else if let array = value as? [Any] {
            let anyCodableArray = array.map { AnyCodable($0) }
            try container.encode(anyCodableArray)
        } else {
            let context = EncodingError.Context(codingPath: container.codingPath, debugDescription: "AnyCodable cannot encode value of type: \(type(of: value))")
            throw EncodingError.invalidValue(value, context)
        }
    }
}

// MARK: - Extensions

extension Notification.Name {
    static let contentProcessingCompleted = Notification.Name("contentProcessingCompleted")
    static let contentDidUpdate = Notification.Name("contentDidUpdate")
}

// MARK: - Backend Response Models

/// Response from backend when creating a bookmark
struct BookmarkCreateResponse: Decodable {
    let id: Int  // Changed from String to Int to match backend response
    let documentId: Int?  // Changed from String to Int
    let url: String
    let title: String
    let description: String?
    let content: String?  // Added content field
    let bookmarkMetadata: [String: Any]?  // Added metadata field
    let isProcessed: Bool?
    let processingStatus: String?
    let createdAt: String
    let updatedAt: String
    let userId: String?  // Added user_id field
    
    enum CodingKeys: String, CodingKey {
        case id, url, title, description, content, createdAt, updatedAt
        case documentId = "document_id"
        case bookmarkMetadata = "bookmark_metadata"
        case isProcessed = "is_processed"
        case processingStatus = "processing_status"
        case userId = "user_id"
    }
    
    // Custom decoder to handle Any type for bookmarkMetadata
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        documentId = try container.decodeIfPresent(Int.self, forKey: .documentId)
        url = try container.decode(String.self, forKey: .url)
        title = try container.decode(String.self, forKey: .title)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        content = try container.decodeIfPresent(String.self, forKey: .content)
        isProcessed = try container.decodeIfPresent(Bool.self, forKey: .isProcessed)
        processingStatus = try container.decodeIfPresent(String.self, forKey: .processingStatus)
        createdAt = try container.decode(String.self, forKey: .createdAt)
        updatedAt = try container.decode(String.self, forKey: .updatedAt)
        userId = try container.decodeIfPresent(String.self, forKey: .userId)
        
        // Handle bookmarkMetadata as Any
        if let metadataData = try container.decodeIfPresent(Data.self, forKey: .bookmarkMetadata) {
            bookmarkMetadata = try JSONSerialization.jsonObject(with: metadataData) as? [String: Any]
        } else {
            bookmarkMetadata = nil
        }
    }
}

/// Response from backend when fetching a bookmark
struct BookmarkResponse: Codable {
    let id: String
    let url: String
    let title: String
    let description: String?
    let documentId: String?
    let isProcessed: Bool
    let processingStatus: String?
    let createdAt: String
    let updatedAt: String
    
    enum CodingKeys: String, CodingKey {
        case id, url, title, description, createdAt, updatedAt
        case documentId = "document_id"
        case isProcessed = "is_processed"
        case processingStatus = "processing_status"
    }
}

