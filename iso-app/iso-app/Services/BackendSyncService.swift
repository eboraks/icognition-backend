//
//  BackendSyncService.swift
//  iso-app
//
//  Service for syncing local articles with the backend
//

import Foundation
import CoreData
import os.log

// MARK: - Backend Sync Service

class BackendSyncService {
    static let shared = BackendSyncService()
    
    private let httpClient = HTTPClient.shared
    private let coreDataStack = CoreDataStack.shared
    
    private init() {}
    
    /// Syncs all local articles with the backend
    /// Checks if each article has a bookmark in the backend, creates one if not
    func syncAllArticles() async {
        AppLogger.content("Starting sync...", level: .info)
        
        let context = coreDataStack.viewContext
        let request: NSFetchRequest<Article> = Article.fetchRequest()
        
        do {
            let articles = try context.fetch(request)
        
            var syncedCount = 0
            var skippedCount = 0
            var createdCount = 0
            var failedCount = 0
            
            for article in articles {
                guard let url = article.url else { continue }
                
                // Skip if article already has backend IDs
                if article.backendBookmarkId != nil {
                    skippedCount += 1
                    continue
                }
                
                // Convert to ArticleData for API calls
                let articleData = convertToArticleData(article)
                
                // Check if bookmark exists in backend
                if let bookmarkData = await checkBookmarkExists(url: url) {
                    // Update local article with backend IDs
                    await updateArticleWithBackendIds(
                        url: url,
                        bookmarkId: String(bookmarkData.id),
                        documentId: bookmarkData.documentId != nil ? String(bookmarkData.documentId!) : nil
                    )
                    syncedCount += 1
                } else {
                    // Create new bookmark in backend
                    if let bookmarkData = await createBookmarkForArticle(articleData) {
                        // Update local article with backend IDs
                        await updateArticleWithBackendIds(
                            url: url,
                            bookmarkId: String(bookmarkData.id),
                            documentId: bookmarkData.documentId != nil ? String(bookmarkData.documentId!) : nil
                        )
                        createdCount += 1
                    } else {
                        failedCount += 1
                    }
                }
            }
            
            AppLogger.content("Sync completed - Synced: \(syncedCount), Created: \(createdCount), Skipped: \(skippedCount), Failed: \(failedCount)", level: .info)
        } catch {
            AppLogger.content("Failed to fetch articles for sync: \(error.localizedDescription)", level: .error)
        }
    }
    
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
    
    /// Checks if a bookmark exists for the given URL
    private func checkBookmarkExists(url: String) async -> BookmarkData? {
        let encodedURL = url.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        let endpoint = "/bookmarks/find?url=\(encodedURL)"
        
        do {
            let (data, statusCode) = try await httpClient.get(endpoint: endpoint, requiresAuth: true)
            
            if statusCode == 200 {
                let bookmarkData = try JSONDecoder().decode(BookmarkData.self, from: data)
                return bookmarkData
            } else if statusCode == 404 {
                return nil
            } else {
                return nil
            }
            
        } catch {
            return nil
        }
    }
    
    /// Creates a new bookmark for an existing article
    private func createBookmarkForArticle(_ article: ArticleData) async -> BookmarkData? {
        // Prepare metadata
        var metadataDict: [String: Any] = [:]
        if let metadata = article.metadata {
            if let author = metadata.author {
                metadataDict["author"] = author
            }
            if let description = metadata.description {
                metadataDict["description"] = description
            }
            if let publishedDate = metadata.publishedDate {
                metadataDict["publishedDate"] = publishedDate
            }
        }
        metadataDict["domain"] = article.domain
        metadataDict["savedAt"] = article.savedAt
        
        let anyCodableMetadata = metadataDict.mapValues { AnyCodable($0) }
        
        let bookmarkRequest = BackendBookmarkCreateRequest(
            url: article.url,
            title: article.title,
            description: article.metadata?.description,
            content: article.content,
            metadata: anyCodableMetadata
        )
        
        do {
            let jsonData = try JSONEncoder().encode(bookmarkRequest)
            let (data, statusCode) = try await httpClient.post(endpoint: "/bookmarks/", body: jsonData, requiresAuth: true)
            
            if !(200...299).contains(statusCode) {
                return nil
            }
            
            let bookmarkData = try JSONDecoder().decode(BookmarkData.self, from: data)
            return bookmarkData
            
        } catch {
            AppLogger.content("Error creating bookmark: \(error.localizedDescription)", level: .error)
            return nil
        }
    }
    
    /// Updates the local article with backend IDs using Core Data
    private func updateArticleWithBackendIds(
        url: String,
        bookmarkId: String,
        documentId: String?
    ) async {
        AppLogger.content("Updating article with backend IDs...", level: .info)
        
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
                }
            } catch {
                AppLogger.content("Failed to update article: \(error.localizedDescription)", level: .error)
            }
        }
    }
}

