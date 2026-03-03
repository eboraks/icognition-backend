//
//  DocumentsAPIService.swift
//  iso-app
//
//  Service for fetching all documents/bookmarks from the backend
//

import Foundation
import os.log

/// Service for fetching all documents from the backend (source of truth)
class DocumentsAPIService {
    static let shared = DocumentsAPIService()
    
    private let httpClient = HTTPClient.shared
    private let logger = Logger(subsystem: "com.icognition.iso-app", category: "DocumentsAPIService")
    
    private init() {}
    
    /// Fetches all documents from the backend with pagination
    /// - Parameters:
    ///   - page: Page number (default: 1)
    ///   - pageSize: Number of items per page (default: 100)
    /// - Returns: Array of DocumentData or empty array if failed
    func fetchAllDocuments(page: Int = 1, pageSize: Int = 100) async -> [DocumentData] {
        logger.info("📥 DocumentsAPIService: Fetching documents (page: \(page), pageSize: \(pageSize))")
        
        do {
            let endpoint = "/documents/?page=\(page)&page_size=\(pageSize)"
            let (data, statusCode) = try await httpClient.get(endpoint: endpoint, requiresAuth: true)
            
            logger.info("📥 DocumentsAPIService: Response status \(statusCode)")
            
            if statusCode == 200 {
                // Try to decode as DocumentsListResponse with "documents" key
                if let response = try? JSONDecoder().decode(DocumentsListResponse.self, from: data) {
                    logger.info("✅ DocumentsAPIService: Fetched \(response.documents.count) documents from paginated response")
                    return response.documents
                }
                // Fallback: try as direct array
                else if let documents = try? JSONDecoder().decode([DocumentData].self, from: data) {
                    logger.info("✅ DocumentsAPIService: Fetched \(documents.count) documents as direct array")
                    return documents
                }
                // If both fail, log the response
                else {
                    logger.warning("⚠️ DocumentsAPIService: Could not decode documents")
                    if let responseString = String(data: data, encoding: .utf8) {
                        logger.debug("📄 Response body: \(responseString.prefix(500))")
                    }
                    return []
                }
            } else {
                logger.error("❌ DocumentsAPIService: API returned status \(statusCode)")
                if let responseString = String(data: data, encoding: .utf8) {
                    logger.error("📄 Response body: \(responseString)")
                }
                return []
            }
            
        } catch {
            logger.error("❌ DocumentsAPIService: Fetch failed: \(error.localizedDescription)")
            return []
        }
    }
    
    /// Converts DocumentData to ArticleData for display in LibraryView
    func convertToArticleData(_ document: DocumentData) -> ArticleData {
        // Create ISO8601 formatter with fractional seconds support
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        dateFormatter.timeZone = TimeZone(secondsFromGMT: 0)  // UTC
        
        // Parse dates - use updated_at from backend as the saved date
        var savedAt = Date()
        if let updatedAtString = document.updatedAt {
            // Try parsing with fractional seconds
            if let parsedDate = dateFormatter.date(from: updatedAtString) {
                savedAt = parsedDate
            } else {
                // Fallback to basic ISO8601 without fractional seconds
                let fallbackFormatter = ISO8601DateFormatter()
                fallbackFormatter.timeZone = TimeZone(secondsFromGMT: 0)
                if let parsedDate = fallbackFormatter.date(from: updatedAtString) {
                    savedAt = parsedDate
                }
            }
        }
        
        // Extract domain from URL
        let domain: String
        if let urlString = document.url, let url = URL(string: urlString) {
            domain = url.host ?? "unknown"
        } else {
            domain = "unknown"
        }
        
        // Create ArticleMetadata if available
        var metadata: ArticleMetadata?
        if let author = document.author {
            let pubDate: Date?
            if let pubDateString = document.publicationDate {
                pubDate = dateFormatter.date(from: pubDateString)
            } else {
                pubDate = savedAt
            }
            metadata = ArticleMetadata(
                description: document.description,
                imageURL: nil,
                author: author,
                publishedDate: pubDate
            )
        }
        
        return ArticleData(
            url: document.url ?? "",
            title: document.title ?? "Untitled",
            domain: domain,
            content: document.content,
            metadata: metadata,
            savedAt: savedAt,
            backendBookmarkId: nil, // We'll map this from bookmarks if needed
            backendDocumentId: String(document.id),
            aiMarkdownContent: document.aiMarkdownContent
        )
    }
}

/// Response structure for paginated documents list from backend
struct DocumentsListResponse: Codable {
    let documents: [DocumentData]
    let total: Int
    let page: Int
    let pageSize: Int
    let totalPages: Int
    
    enum CodingKeys: String, CodingKey {
        case documents
        case total
        case page
        case pageSize = "page_size"
        case totalPages = "total_pages"
    }
}

