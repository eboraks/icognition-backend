//
//  DocumentAPIService.swift
//  iso-app
//
//  Service for fetching document data with AI content from the backend
//

import Foundation
import os.log

/// Service for fetching document data with AI content from the backend
class DocumentAPIService {
    static let shared = DocumentAPIService()
    
    private let logger = Logger(subsystem: "com.icognition.iso-app", category: "DocumentAPIService")
    private let httpClient = HTTPClient.shared
    
    private init() {}
    
    /// Fetches document data with AI-generated content
    /// - Parameter documentId: The document ID from the backend
    /// - Returns: DocumentData with AI content or nil if failed
    func fetchDocument(documentId: String) async -> DocumentData? {
        
        logger.info("🔍 DocumentAPIService: Fetching document \(documentId)")
        
        do {
            let (data, statusCode) = try await httpClient.get(endpoint: "/documents/\(documentId)", requiresAuth: true)
            
            logger.info("📥 DocumentAPIService: Document response status \(statusCode)")
            
            if statusCode == 200 {
                let documentData = try JSONDecoder().decode(DocumentData.self, from: data)
                logger.info("✅ DocumentAPIService: Document fetched successfully")
                
                // Log AI content status
                if let markdown = documentData.aiMarkdownContent, !markdown.isEmpty {
                    logger.info("📝 DocumentAPIService: AI Markdown content available (\(markdown.count) chars)")
                } else {
                    logger.info("⚠️ DocumentAPIService: No AI Markdown content available")
                }
                
                return documentData
            } else {
                logger.error("❌ DocumentAPIService: Document API returned status \(statusCode)")
                if let responseString = String(data: data, encoding: .utf8) {
                    logger.error("📄 DocumentAPIService: Response body: \(responseString)")
                }
                return nil
            }
            
        } catch {
            logger.error("❌ DocumentAPIService: Document fetch failed: \(error.localizedDescription)")
            return nil
        }
    }
    
    /// Checks if document has AI content available
    /// - Parameter documentId: The document ID
    /// - Returns: True if document has ai_markdown_content
    func hasAIContent(documentId: String) async -> Bool {
        guard let document = await fetchDocument(documentId: documentId) else {
            return false
        }
        return document.aiMarkdownContent != nil && !document.aiMarkdownContent!.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

