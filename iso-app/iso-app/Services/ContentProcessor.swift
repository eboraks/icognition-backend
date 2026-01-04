//
//  ContentProcessor.swift
//  iso-app
//
//  Processes content saved by the Share Extension and integrates it into the main app
//

import Foundation
import Combine
import UIKit
import os.log
import FirebaseAuth
import CoreData

/// Processes content saved by the Share Extension and integrates it into the main app
@MainActor
class ContentProcessor: ObservableObject {
    static let shared = ContentProcessor()
    
    @Published var isProcessing = false
    @Published var processedCount = 0
    @Published var lastProcessedContent: ProcessedContent?
    @Published var errorMessage: String?
    
    private let sharedDataManager = SharedDataManager.shared
    private var cancellables = Set<AnyCancellable>()
    private var fileWatcher: DispatchSourceFileSystemObject?
    private var htmlCacheURL: URL?
    
    private init() {
        startMonitoring()
        setupFileWatcher()
    }
    
    // MARK: - Monitoring Setup
    
    /// Start monitoring for new content from Share Extension
    func startMonitoring() {
        AppLogger.content("Starting content monitoring", level: .info)
        
        // Check for pending content on initialization
        processPendingContent()
        
        // File watcher handles automatic detection of new files
        // No need for periodic checks or app activation handlers
    }
    
    // MARK: - Content Processing
    
    /// Process all pending content from Share Extension
    func processPendingContent() {
        guard !isProcessing else {
            AppLogger.content("Content processing already in progress", level: .debug)
            return
        }
        
        isProcessing = true
        errorMessage = nil
        
        Task {
            do {
                let pendingContent = sharedDataManager.getPendingSharedContent()
                AppLogger.content("Found \(pendingContent.count) pending content items", level: .info)
                
                var processedItems: [ProcessedContent] = []
                
                for content in pendingContent {
                    do {
                        let processedContent = try await processContentItem(content)
                        processedItems.append(processedContent)
                        
                        // Mark as processed
                        try sharedDataManager.markContentAsProcessed(id: content.id)
                        
                        AppLogger.content("Processed content: \(content.title)", level: .info)
                    } catch {
                        AppLogger.content("Failed to process content \(content.id): \(error.localizedDescription)", level: .error)
                        errorMessage = "Failed to process some content: \(error.localizedDescription)"
                    }
                }
                
                // Update UI state
                await MainActor.run {
                    self.processedCount += processedItems.count
                    if let lastItem = processedItems.last {
                        self.lastProcessedContent = lastItem
                    }
                    self.isProcessing = false
                }
                
                // Post notification for UI updates
                NotificationCenter.default.post(
                    name: .contentProcessingCompleted,
                    object: processedItems
                )
                
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                    self.isProcessing = false
                }
            }
        }
    }
    
    /// Process a single content item
    private func processContentItem(_ content: SharedContentItem) async throws -> ProcessedContent {
        AppLogger.content("Processing content: \(content.title)", level: .info)
        
        // Get metadata if available
        var metadata: [String: Any] = [:]
        do {
            metadata = try sharedDataManager.getMetadataForContent(id: content.id)
        } catch {
            AppLogger.content("No metadata found for content \(content.id)", level: .warning)
        }
        
        // Check if Article already exists in Core Data (ShareExtension now saves directly)
        let coreDataStack = CoreDataStack.shared
        let context = coreDataStack.viewContext
        let request: NSFetchRequest<Article> = Article.fetchRequest()
        request.predicate = NSPredicate(format: "url == %@", content.url.absoluteString)
        request.fetchLimit = 1
        
        let existingArticle = try? context.fetch(request).first
        
        let articleData: ArticleData
        if let existing = existingArticle {
            // Use existing Article (ShareExtension already saved it)
            articleData = convertToArticleData(existing)
            AppLogger.content("Using existing Article for: \(content.title)", level: .info)
        } else {
            // Create new ArticleData (fallback for old pending content)
            articleData = ArticleData(
                url: content.url.absoluteString,
                title: content.title,
                domain: extractDomain(from: content.url),
                content: nil, // ContentProcessor doesn't extract content, only share extension does
                metadata: ArticleMetadata(
                    description: metadata["linkDescription"] as? String,
                    imageURL: metadata["linkImageURL"] as? String,
                    author: metadata["author"] as? String,
                    publishedDate: nil // Could be extracted from metadata
                )
            )
            AppLogger.content("Created new ArticleData for: \(content.title)", level: .info)
            
            // Save to Core Data (fallback for old pending content)
            sharedDataManager.saveArticleData(articleData)
            AppLogger.content("Saved new ArticleData to Core Data for: \(content.title)", level: .info)
        }
        
        // Create processed content object
        let processedContent = ProcessedContent(
            id: content.id,
            title: content.title,
            url: content.url,
            domain: extractDomain(from: content.url),
            timestamp: content.timestamp,
            metadata: metadata,
            articleData: articleData
        )
        
        // Sync to backend if user is authenticated
        await syncToBackend(articleData: articleData)
        
        return processedContent
    }
    
    /// Sync article to backend if user is authenticated
    private func syncToBackend(articleData: ArticleData) async {
        // Check if user is authenticated
        guard let currentUser = getCurrentAuthenticatedUser() else {
            AppLogger.content("User not authenticated, skipping backend sync", level: .warning)
            return
        }
        
        AppLogger.content("Syncing article to backend: \(articleData.title)", level: .info)
        
        do {
            // Call backend API to create bookmark
            let response = await createBackendBookmark(
                articleData: articleData
            )
            
            if let response = response {
                AppLogger.content("Backend sync successful", level: .info)
                AppLogger.content("Bookmark ID: \(response.id)", level: .debug)
                AppLogger.content("Document ID: \(response.documentId != nil ? String(response.documentId!) : "nil")", level: .debug)
                
                // Update ArticleData with both IDs immediately
                await updateArticleWithBackendIds(
                    url: articleData.url,
                    bookmarkId: String(response.id),
                    documentId: response.documentId != nil ? String(response.documentId!) : nil
                )
                
                // Trigger AI content polling if document_id is available
                if let documentId = response.documentId {
                    AppLogger.content("Starting AI content polling for document \(documentId)", level: .info)
                    DocumentPollingService.shared.startPolling(documentId: String(documentId))
                } else {
                    AppLogger.content("No document_id in response yet", level: .warning)
                }
            } else {
                AppLogger.content("Backend sync failed", level: .error)
            }
            
        } catch {
            AppLogger.content("Backend sync error: \(error.localizedDescription)", level: .error)
        }
    }
    
    /// Get current authenticated user
    private func getCurrentAuthenticatedUser() -> String? {
        // Check shared UserDefaults for current user
        guard let sharedDefaults = UserDefaults(suiteName: "group.com.icognition.app"),
              let userID = sharedDefaults.string(forKey: "testUserID") else {
            return nil
        }
        return userID
    }
    
    
    /// Create bookmark on backend
    private func createBackendBookmark(
        articleData: ArticleData
    ) async -> BookmarkData? {
        // Read HTML from disk if available
        var htmlContent: String? = nil
        
        if articleData.hasLocalHTML,
           let htmlFilePath = articleData.htmlFilePath,
           let htmlURL = sharedDataManager.getHTMLFileURL(relativePath: htmlFilePath) {
            do {
                htmlContent = try String(contentsOf: htmlURL, encoding: .utf8)
                AppLogger.content("Read HTML: \(htmlFilePath) (\(htmlContent?.count ?? 0) chars)", level: .info)
                
                if let content = htmlContent, content.isEmpty {
                    AppLogger.content("HTML file is empty", level: .warning)
                }
            } catch {
                AppLogger.content("Failed to read HTML: \(error.localizedDescription)", level: .error)
            }
        } else if !articleData.hasLocalHTML {
            AppLogger.content("No local HTML available for this article", level: .info)
        }
        
        // Prepare request data with HTML content
        let contentToSend = htmlContent ?? ""
        var bookmarkData: [String: Any] = [
            "url": articleData.url,
            "title": articleData.title,
            "description": articleData.metadata?.description ?? "",
            "content": contentToSend,  // Raw HTML content here
            "metadata": [
                "domain": articleData.domain,
                "source": "ios_share_extension",
                "timestamp": Date().timeIntervalSince1970,
                "hasLocalHTML": articleData.hasLocalHTML,
                "contentStatus": contentToSend == "NOT_AVAILABLE" ? "limited" : "full"
            ]
        ]
        
        // Make API request using HTTPClient
        do {
            let jsonData = try JSONSerialization.data(withJSONObject: bookmarkData, options: [])
            
            let contentDescription = contentToSend == "NOT_AVAILABLE" ? "NOT_AVAILABLE" : "\(contentToSend.count) chars"
            AppLogger.network("Creating bookmark: \(articleData.title) (\(contentDescription))", level: .info)
            
            // Proactively refresh token before making the request
            AppLogger.auth("Proactively refreshing Firebase token before bookmark creation", level: .info)
            if let user = Auth.auth().currentUser {
                do {
                    _ = try await user.getIDToken(forcingRefresh: true)
                    AppLogger.auth("Token refreshed successfully", level: .info)
                } catch {
                    AppLogger.auth("Proactive token refresh failed: \(error.localizedDescription)", level: .warning)
                    // Continue anyway, HTTPClient will handle retry on 401
                }
            }
            
            let (data, statusCode) = try await HTTPClient.shared.post(
                endpoint: "/bookmarks/",
                body: jsonData,
                requiresAuth: true
            )
            
            AppLogger.network("Received response with status \(statusCode)", level: .info)
            
            guard statusCode == 200 || statusCode == 201 else {
                AppLogger.network("HTTP error \(statusCode)", level: .error)
                return nil
            }
            
            // Log the raw response data for debugging (truncated to 200 characters)
            if let responseString = String(data: data, encoding: .utf8) {
                let truncatedResponse = responseString.count > 200 
                    ? String(responseString.prefix(200)) + "..." 
                    : responseString
                AppLogger.network("Raw response data: \(truncatedResponse)", level: .debug)
            } else {
                AppLogger.network("Response data is not valid UTF-8", level: .error)
            }
            
            let decoder = JSONDecoder()
            let bookmarkResponse = try decoder.decode(BookmarkData.self, from: data)
            AppLogger.content("Bookmark created successfully", level: .info)
            return bookmarkResponse
            
        } catch {
            AppLogger.content("Error creating bookmark: \(error.localizedDescription)", level: .error)
            
            // Add more detailed error information for debugging
            if let decodingError = error as? DecodingError {
                switch decodingError {
                case .typeMismatch(let type, let context):
                    AppLogger.content("Decoding error - Type mismatch: expected \(type), context: \(context)", level: .error)
                case .valueNotFound(let type, let context):
                    AppLogger.content("Decoding error - Value not found: \(type), context: \(context)", level: .error)
                case .keyNotFound(let key, let context):
                    AppLogger.content("Decoding error - Key not found: \(key), context: \(context)", level: .error)
                case .dataCorrupted(let context):
                    AppLogger.content("Decoding error - Data corrupted: \(context)", level: .error)
                @unknown default:
                    AppLogger.content("Decoding error - Unknown: \(decodingError)", level: .error)
                }
            }
            
            return nil
        }
    }
    
    /// Update ArticleData with backend IDs using Core Data
    private func updateArticleWithBackendIds(
        url: String,
        bookmarkId: String,
        documentId: String?
    ) async {
        AppLogger.content("Updating article with backend IDs...", level: .info)
        
        let coreDataStack = CoreDataStack.shared
        let context = coreDataStack.newBackgroundContext()
        
        await context.perform {
            let request: NSFetchRequest<Article> = Article.fetchRequest()
            request.predicate = NSPredicate(format: "url == %@", url)
            request.fetchLimit = 1
            
            do {
                let articles = try context.fetch(request)
                if let article = articles.first {
                    article.backendBookmarkId = bookmarkId
                    article.backendDocumentId = documentId
                    article.lastSyncedAt = Date()
                    
                    try context.save()
                    AppLogger.content("Article updated with backend IDs", level: .info)
                    AppLogger.content("Bookmark ID: \(bookmarkId)", level: .debug)
                    AppLogger.content("Document ID: \(documentId ?? "nil")", level: .debug)
                } else {
                    AppLogger.content("Could not find article to update with backend IDs", level: .warning)
                }
            } catch {
                AppLogger.content("Failed to update article with backend IDs: \(error.localizedDescription)", level: .error)
            }
        }
    }
    
    // MARK: - Helper Methods
    
    /// Convert Core Data Article to ArticleData
    private func convertToArticleData(_ article: Article) -> ArticleData {
        var metadata: ArticleMetadata? = nil
        if article.metadataDescription != nil || article.metadataImageURL != nil || article.metadataAuthor != nil {
            metadata = ArticleMetadata(
                description: article.metadataDescription,
                imageURL: article.metadataImageURL,
                author: article.metadataAuthor,
                publishedDate: article.metadataPublishedDate
            )
        }
        
        return ArticleData(
            url: article.url ?? "",
            title: article.title ?? "",
            domain: article.domain ?? "",
            content: article.content,
            metadata: metadata,
            savedAt: article.savedAt ?? Date(),
            backendBookmarkId: article.backendBookmarkId,
            backendDocumentId: article.backendDocumentId,
            aiSummary: article.aiSummary,
            aiBulletPoints: article.aiBulletPoints as? [String],
            htmlFilePath: article.htmlFilePath,
            hasLocalHTML: article.hasLocalHTML
        )
    }
    
    private func extractDomain(from url: URL) -> String {
        return url.host?.replacingOccurrences(of: "www.", with: "") ?? url.absoluteString
    }
    
    /// Clear any error messages
    func clearError() {
        errorMessage = nil
    }
    
    /// Get processing statistics
    func getProcessingStats() -> ProcessingStats {
        return ProcessingStats(
            isProcessing: isProcessing,
            processedCount: processedCount,
            lastProcessedAt: lastProcessedContent?.timestamp
        )
    }
    
    /// Force refresh of pending content
    func refreshPendingContent() {
        processPendingContent()
    }
    
    // MARK: - File Watcher
    
    /// Set up file system watcher for HTML cache directory
    func setupFileWatcher() {
        // Get the HTML cache directory from App Group container
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: "group.com.icognition.app"
        ) else {
            AppLogger.content("Cannot access App Group container for file watching", level: .error)
            return
        }
        
        let htmlDirectory = containerURL.appendingPathComponent("html_cache")
        htmlCacheURL = htmlDirectory
        
        // Create directory if it doesn't exist
        try? FileManager.default.createDirectory(
            at: htmlDirectory,
            withIntermediateDirectories: true
        )
        
        // Open the directory for monitoring
        let fd = open(htmlDirectory.path, O_EVTONLY)
        guard fd >= 0 else {
            AppLogger.content("Failed to open directory for monitoring: \(errno)", level: .error)
            return
        }
        
        // Create a dispatch source to monitor the directory
        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fd,
            eventMask: .write,
            queue: DispatchQueue.global(qos: .background)
        )
        
        // Set up event handler
        source.setEventHandler { [weak self] in
            AppLogger.content("Detected file change in HTML cache directory", level: .info)
            
            // Small delay to let file write complete
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                self?.processPendingContent()
            }
        }
        
        // Set up cancellation handler
        source.setCancelHandler {
            close(fd)
        }
        
        // Start monitoring
        source.resume()
        fileWatcher = source
        
        AppLogger.content("File watcher started for: \(htmlDirectory.path)", level: .info)
    }
    
    deinit {
        fileWatcher?.cancel()
    }
}

