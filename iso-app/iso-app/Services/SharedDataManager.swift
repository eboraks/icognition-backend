//
//  SharedDataManager.swift
//  iso-app
//
//  Manages shared data between the main app and Share Extension
//

import Foundation
import Combine
import CoreData
import os.log

class SharedDataManager: ObservableObject {
    static let shared = SharedDataManager()
    
    private let appGroupIdentifier = "group.com.icognition.app"
    private let articlesFileName = "saved_articles.json"
    private let pendingContentFileName = "pending_content.json"
    private let coreDataStack = CoreDataStack.shared
    
    private init() {}
    
    // MARK: - Article Data Management (Core Data)
    
    func saveArticleData(_ article: ArticleData) {
        let context = coreDataStack.viewContext
        
        // Check if article with same URL already exists
        let request: NSFetchRequest<Article> = Article.fetchRequest()
        request.predicate = NSPredicate(format: "url == %@", article.url)
        request.fetchLimit = 1
        
        do {
            let existingArticles = try context.fetch(request)
            
            if let existingArticle = existingArticles.first {
                // Update existing article
                updateArticle(existingArticle, with: article)
                AppLogger.storage("Updated existing article: \(article.title)", level: .info)
            } else {
                // Create new article
                let newArticle = Article(context: context)
                updateArticle(newArticle, with: article)
                AppLogger.storage("Added new article: \(article.title)", level: .info)
            }
            
            try context.save()
        } catch {
            AppLogger.storage("Failed to save article to Core Data: \(error.localizedDescription)", level: .error)
        }
    }
    
    func getAllSavedArticles() -> [ArticleData] {
        let context = coreDataStack.viewContext
        let request: NSFetchRequest<Article> = Article.fetchRequest()
        request.sortDescriptors = [NSSortDescriptor(keyPath: \Article.savedAt, ascending: false)]
        
        do {
            let articles = try context.fetch(request)
            return articles.map { articleToArticleData($0) }
        } catch {
            AppLogger.storage("Failed to fetch articles from Core Data: \(error.localizedDescription)", level: .error)
            return []
        }
    }
    
    // Alias for compatibility
    func getAllArticles() -> [ArticleData] {
        return getAllSavedArticles()
    }
    
    /// Convert Core Data Article to ArticleData
    private func articleToArticleData(_ article: Article) -> ArticleData {
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
            htmlFilePath: article.htmlFilePath,
            hasLocalHTML: article.hasLocalHTML
        )
    }

    /// Update Core Data Article with ArticleData
    private func updateArticle(_ article: Article, with articleData: ArticleData) {
        article.url = articleData.url
        article.title = articleData.title
        article.domain = articleData.domain
        article.content = articleData.content
        article.savedAt = articleData.savedAt
        article.backendBookmarkId = articleData.backendBookmarkId
        article.backendDocumentId = articleData.backendDocumentId
        article.htmlFilePath = articleData.htmlFilePath
        article.hasLocalHTML = articleData.hasLocalHTML
        
        // Update metadata
        if let metadata = articleData.metadata {
            article.metadataDescription = metadata.description
            article.metadataImageURL = metadata.imageURL
            article.metadataAuthor = metadata.author
            article.metadataPublishedDate = metadata.publishedDate
        }
        
        // Set ID if not already set
        if article.id == nil {
            article.id = UUID()
        }
    }
    
    /// Get full URL for HTML file stored in App Group container
    func getHTMLFileURL(relativePath: String) -> URL? {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupIdentifier
        ) else {
            AppLogger.storage("Failed to get container URL for app group", level: .error)
            return nil
        }
        return containerURL.appendingPathComponent(relativePath)
    }
    
    func saveArticles(_ articles: [ArticleData]) {
        // Save each article individually using Core Data
        for article in articles {
            saveArticleData(article)
        }
    }
    
    func deleteArticle(with url: String) {
        let context = coreDataStack.viewContext
        let request: NSFetchRequest<Article> = Article.fetchRequest()
        request.predicate = NSPredicate(format: "url == %@", url)
        request.fetchLimit = 1
        
        do {
            let articles = try context.fetch(request)
            if let article = articles.first {
                context.delete(article)
                try context.save()
                AppLogger.storage("Deleted article: \(url)", level: .info)
            }
        } catch {
            AppLogger.storage("Failed to delete article: \(error.localizedDescription)", level: .error)
        }
    }
    
    // MARK: - Pending Content Management
    
    func saveSharedContent(title: String, url: URL, metadata: [String: Any]) {
        let contentItem = SharedContentItem(title: title, url: url, metadata: metadata)
        var pendingContent = getPendingSharedContent()
        pendingContent.append(contentItem)
        savePendingContent(pendingContent)
        
        // Also save metadata separately
        saveMetadata(for: contentItem.id, metadata: metadata)
    }
    
    func getPendingSharedContent() -> [SharedContentItem] {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            AppLogger.storage("Failed to get container URL for app group", level: .error)
            return []
        }
        
        let fileURL = containerURL.appendingPathComponent(pendingContentFileName)
        
        guard let data = try? Data(contentsOf: fileURL) else {
            AppLogger.storage("No pending content file found", level: .debug)
            return []
        }
        
        do {
            let content = try JSONDecoder().decode([SharedContentItem].self, from: data)
            AppLogger.storage("Loaded \(content.count) pending content items", level: .info)
            return content
        } catch {
            AppLogger.storage("Failed to decode pending content: \(error)", level: .error)
            return []
        }
    }
    
    private func savePendingContent(_ content: [SharedContentItem]) {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            AppLogger.storage("Failed to get container URL for app group", level: .error)
            return
        }
        
        let fileURL = containerURL.appendingPathComponent(pendingContentFileName)
        
        do {
            let data = try JSONEncoder().encode(content)
            try data.write(to: fileURL)
            AppLogger.storage("Saved \(content.count) pending content items", level: .info)
        } catch {
            AppLogger.storage("Failed to save pending content: \(error)", level: .error)
        }
    }
    
    func markContentAsProcessed(id: String) throws {
        var pendingContent = getPendingSharedContent()
        pendingContent.removeAll { $0.id == id }
        savePendingContent(pendingContent)
        
        // Remove metadata file
        removeMetadata(for: id)
        
        AppLogger.storage("Marked content \(id) as processed", level: .debug)
    }
    
    // MARK: - Metadata Management
    
    private func saveMetadata(for contentId: String, metadata: [String: Any]) {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            AppLogger.storage("Failed to get container URL for app group", level: .error)
            return
        }
        
        let metadataURL = containerURL.appendingPathComponent("\(contentId).metadata.json")
        
        do {
            let data = try JSONSerialization.data(withJSONObject: metadata, options: .prettyPrinted)
            try data.write(to: metadataURL)
            AppLogger.storage("Saved metadata for content \(contentId)", level: .info)
        } catch {
            AppLogger.storage("Failed to save metadata: \(error)", level: .error)
        }
    }
    
    func getMetadataForContent(id: String) throws -> [String: Any] {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            throw SharedDataError.containerAccessFailed
        }
        
        let metadataURL = containerURL.appendingPathComponent("\(id).metadata.json")
        
        guard let data = try? Data(contentsOf: metadataURL) else {
            throw SharedDataError.metadataNotFound
        }
        
        guard let metadata = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw SharedDataError.metadataDecodeFailed
        }
        
        return metadata
    }
    
    private func removeMetadata(for contentId: String) {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            return
        }
        
        let metadataURL = containerURL.appendingPathComponent("\(contentId).metadata.json")
        
        do {
            try FileManager.default.removeItem(at: metadataURL)
            AppLogger.storage("Removed metadata for content \(contentId)", level: .info)
        } catch {
            AppLogger.storage("Failed to remove metadata: \(error)", level: .error)
        }
    }
    
    // MARK: - Utility Methods
    
    func clearPendingData() {
        guard let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            return
        }
        
        let fileURL = containerURL.appendingPathComponent(pendingContentFileName)
        
        do {
            try FileManager.default.removeItem(at: fileURL)
            AppLogger.storage("Cleared pending content data", level: .info)
        } catch {
            AppLogger.storage("Failed to clear pending data: \(error)", level: .error)
        }
    }
    
    func clearAllData() {
        clearPendingData()
        
        // Delete all articles from Core Data
        let context = coreDataStack.viewContext
        let request: NSFetchRequest<NSFetchRequestResult> = Article.fetchRequest()
        let deleteRequest = NSBatchDeleteRequest(fetchRequest: request)
        
        do {
            try context.execute(deleteRequest)
            try context.save()
            AppLogger.storage("Cleared all article data from Core Data", level: .info)
        } catch {
            AppLogger.storage("Failed to clear article data: \(error.localizedDescription)", level: .error)
        }
    }
    
    /// Clean up HTML files older than 5 days
    func cleanupOldHTMLFiles() {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupIdentifier
        ) else { return }
        
        let htmlDirectory = containerURL.appendingPathComponent("html_cache")
        guard let files = try? FileManager.default.contentsOfDirectory(at: htmlDirectory, includingPropertiesForKeys: [.creationDateKey]) else {
            return
        }
        
        let fiveDaysAgo = Date().addingTimeInterval(-5 * 24 * 60 * 60)
        
        for file in files {
            if let attributes = try? FileManager.default.attributesOfItem(atPath: file.path),
               let creationDate = attributes[.creationDate] as? Date,
               creationDate < fiveDaysAgo {
                try? FileManager.default.removeItem(at: file)
                AppLogger.storage("Cleaned up old HTML file: \(file.lastPathComponent)", level: .debug)
            }
        }
    }
    
    /// Debug method to list all saved HTML files
    func listSavedHTMLFiles() -> [(name: String, size: Int64, date: Date, path: String)] {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupIdentifier
        ) else {
            AppLogger.storage("Cannot access App Group container for file listing", level: .error)
            return []
        }
        
        let htmlDirectory = containerURL.appendingPathComponent("html_cache")
        
        do {
            let files = try FileManager.default.contentsOfDirectory(at: htmlDirectory, includingPropertiesForKeys: [.fileSizeKey, .creationDateKey])
            var fileInfo: [(name: String, size: Int64, date: Date, path: String)] = []
            
            for file in files {
                let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
                let fileSize = attributes[.size] as? Int64 ?? 0
                let creationDate = attributes[.creationDate] as? Date ?? Date()
                
                fileInfo.append((
                    name: file.lastPathComponent,
                    size: fileSize,
                    date: creationDate,
                    path: file.path
                ))
            }
            
            AppLogger.storage("📁 Found \(fileInfo.count) HTML files for debugging", level: .info)
            return fileInfo.sorted { $0.date > $1.date } // Most recent first
        } catch {
            AppLogger.storage("Failed to list HTML files: \(error.localizedDescription)", level: .error)
            return []
        }
    }
}

// MARK: - Errors

enum SharedDataError: LocalizedError {
    case containerAccessFailed
    case metadataNotFound
    case metadataDecodeFailed
    case saveFailed
    
    var errorDescription: String? {
        switch self {
        case .containerAccessFailed:
            return "Failed to access app group container"
        case .metadataNotFound:
            return "Metadata file not found"
        case .metadataDecodeFailed:
            return "Failed to decode metadata"
        case .saveFailed:
            return "Failed to save data"
        }
    }
}

