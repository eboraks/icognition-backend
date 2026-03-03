//
//  CoreDataMigrationService.swift
//  iso-app
//
//  Service to migrate existing JSON data to Core Data
//

import Foundation
import CoreData
import os.log

/// Service to migrate data from JSON files to Core Data
class CoreDataMigrationService {
    static let shared = CoreDataMigrationService()
    
    private let sharedDataManager = SharedDataManager.shared
    private let coreDataStack = CoreDataStack.shared
    
    private init() {}
    
    /// Check if migration has already been performed
    func hasMigrated() -> Bool {
        let defaults = UserDefaults(suiteName: "group.com.icognition.app")
        return defaults?.bool(forKey: "CoreDataMigrationCompleted") ?? false
    }
    
    /// Mark migration as completed
    private func markMigrationCompleted() {
        let defaults = UserDefaults(suiteName: "group.com.icognition.app")
        defaults?.set(true, forKey: "CoreDataMigrationCompleted")
        defaults?.synchronize()
    }
    
    /// Reset migration flag - allows migration to run again
    func resetMigrationFlag() {
        let defaults = UserDefaults(suiteName: "group.com.icognition.app")
        defaults?.removeObject(forKey: "CoreDataMigrationCompleted")
        defaults?.synchronize()
        AppLogger.storage("Migration flag reset", level: .info)
    }
    
    /// Migrate all existing JSON data to Core Data
    func migrateFromJSON() async throws {
        guard !hasMigrated() else {
            AppLogger.storage("Migration already completed, skipping", level: .info)
            return
        }
        
        AppLogger.storage("Starting Core Data migration from JSON", level: .info)
        
        let context = coreDataStack.newBackgroundContext()
        
        return try await context.perform {
            // Migrate articles
            let articles = self.sharedDataManager.getAllSavedArticles()
            AppLogger.storage("Migrating \(articles.count) articles to Core Data", level: .info)
            
            for articleData in articles {
                // Check if article already exists (by URL)
                let request: NSFetchRequest<Article> = Article.fetchRequest()
                request.predicate = NSPredicate(format: "url == %@", articleData.url)
                request.fetchLimit = 1
                
                let existingArticles = try context.fetch(request)
                
                if let existingArticle = existingArticles.first {
                    // Update existing article
                    self.updateArticle(existingArticle, with: articleData)
                    AppLogger.storage("Updated existing article: \(articleData.title)", level: .debug)
                } else {
                    // Create new article
                    let article = Article(context: context)
                    self.updateArticle(article, with: articleData)
                    AppLogger.storage("Created new article: \(articleData.title)", level: .debug)
                }
            }
            
            // Save context
            try context.save()
            AppLogger.storage("Core Data migration completed successfully", level: .info)
            
            // Mark migration as completed
            self.markMigrationCompleted()
        }
    }
    
    /// Update a Core Data Article entity with ArticleData
    private func updateArticle(_ article: Article, with articleData: ArticleData) {
        article.id = UUID()
        article.url = articleData.url
        article.title = articleData.title
        article.domain = articleData.domain
        article.content = articleData.content
        article.savedAt = articleData.savedAt
        article.backendBookmarkId = articleData.backendBookmarkId
        article.backendDocumentId = articleData.backendDocumentId
        article.htmlFilePath = articleData.htmlFilePath
        article.hasLocalHTML = articleData.hasLocalHTML
        article.lastSyncedAt = nil // Will be set when synced with backend
        
        // Migrate metadata
        if let metadata = articleData.metadata {
            article.metadataDescription = metadata.description
            article.metadataImageURL = metadata.imageURL
            article.metadataAuthor = metadata.author
            article.metadataPublishedDate = metadata.publishedDate
        }
    }
}

