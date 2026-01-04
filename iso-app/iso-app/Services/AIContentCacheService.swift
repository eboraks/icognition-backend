//
//  AIContentCacheService.swift
//  iso-app
//
//  Service for pre-fetching and caching AI-generated content locally
//

import Foundation
import os.log

/// Service for pre-fetching and caching AI-generated summaries and bullet points
class AIContentCacheService {
    static let shared = AIContentCacheService()
    
    private let cacheKey = "ai_content_cache"
    private let sharedDefaults = UserDefaults(suiteName: "group.com.icognition.app")
    
    private init() {}
    
    // MARK: - Cached Content Model
    
    /// Cached AI content structure
    struct CachedAIContent: Codable {
        let documentId: String
        let summary: String?
        let bulletPoints: [String]?
        let cachedAt: Date
        let expiresAt: Date
    }
    
    // MARK: - Cache Operations
    
    /// Pre-fetch AI content and cache locally
    func prefetchAndCache(documentId: String) async {
        // Check if already cached and fresh
        if let cached = getCachedContent(documentId: documentId),
           cached.expiresAt > Date() {
            AppLogger.ai("Using cached AI content for \(documentId)", level: .info)
            return
        }
        
        AppLogger.ai("Fetching AI content for document \(documentId)", level: .info)
        
        // Fetch from backend
        if let documentData = await DocumentAPIService.shared.fetchDocument(documentId: documentId) {
            let content = CachedAIContent(
                documentId: documentId,
                summary: documentData.aiIsAbout,
                bulletPoints: documentData.aiBulletPoints,
                cachedAt: Date(),
                expiresAt: Date().addingTimeInterval(7 * 24 * 60 * 60) // 7 days
            )
            saveToCache(content: content)
            AppLogger.ai("Cached AI content for \(documentId)", level: .info)
        } else {
            AppLogger.ai("Failed to fetch AI content for \(documentId)", level: .warning)
        }
    }
    
    /// Get cached content if available and not expired
    func getCachedContent(documentId: String) -> CachedAIContent? {
        guard let data = sharedDefaults?.data(forKey: "\(cacheKey)_\(documentId)"),
              let cached = try? JSONDecoder().decode(CachedAIContent.self, from: data) else {
            return nil
        }
        
        // Check if cache is expired
        if cached.expiresAt > Date() {
            return cached
        } else {
            // Remove expired cache
            clearCache(documentId: documentId)
            return nil
        }
    }
    
    /// Save content to cache
    private func saveToCache(content: CachedAIContent) {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(content)
            sharedDefaults?.set(data, forKey: "\(cacheKey)_\(content.documentId)")
            AppLogger.ai("Saved cache for document \(content.documentId)", level: .debug)
        } catch {
            AppLogger.ai("Failed to save cache: \(error)", level: .error)
        }
    }
    
    /// Clear cache for specific document
    func clearCache(documentId: String) {
        sharedDefaults?.removeObject(forKey: "\(cacheKey)_\(documentId)")
        AppLogger.ai("Cleared cache for document \(documentId)", level: .debug)
    }
    
    /// Clear all cached content
    func clearAllCache() {
        guard let defaults = sharedDefaults else { return }
        
        let allKeys = defaults.dictionaryRepresentation().keys
        let cacheKeys = allKeys.filter { $0.hasPrefix(cacheKey) }
        
        for key in cacheKeys {
            defaults.removeObject(forKey: key)
        }
        
        AppLogger.ai("Cleared all cached content (\(cacheKeys.count) items)", level: .info)
    }
    
    // MARK: - Batch Operations
    
    /// Batch pre-fetch for all articles in library
    func prefetchAllArticles(articles: [ArticleData]) async {
        let articlesNeedingCache = articles.filter { article in
            guard let docId = article.backendDocumentId else { return false }
            return getCachedContent(documentId: docId) == nil
        }
        
        guard !articlesNeedingCache.isEmpty else {
            AppLogger.ai("All articles already cached", level: .info)
            return
        }
        
        AppLogger.ai("Pre-fetching AI content for \(articlesNeedingCache.count) articles", level: .info)
        
        for (index, article) in articlesNeedingCache.enumerated() {
            if let docId = article.backendDocumentId {
                AppLogger.ai("Fetching \(index + 1)/\(articlesNeedingCache.count): \(article.title)", level: .debug)
                await prefetchAndCache(documentId: docId)
                
                // Small delay to avoid overwhelming backend
                if index < articlesNeedingCache.count - 1 {
                    try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s
                }
            }
        }
        
        AppLogger.ai("Completed pre-fetching for \(articlesNeedingCache.count) articles", level: .info)
    }
    
    // MARK: - Cache Statistics
    
    /// Get statistics about cached content
    func getCacheStatistics() -> (total: Int, expired: Int, valid: Int) {
        guard let defaults = sharedDefaults else {
            return (0, 0, 0)
        }
        
        let allKeys = defaults.dictionaryRepresentation().keys
        let cacheKeys = allKeys.filter { $0.hasPrefix(cacheKey) }
        
        var expiredCount = 0
        var validCount = 0
        
        for key in cacheKeys {
            if let data = defaults.data(forKey: key),
               let cached = try? JSONDecoder().decode(CachedAIContent.self, from: data) {
                if cached.expiresAt > Date() {
                    validCount += 1
                } else {
                    expiredCount += 1
                }
            }
        }
        
        return (total: cacheKeys.count, expired: expiredCount, valid: validCount)
    }
    
    /// Clean up expired cache entries
    func cleanupExpiredCache() {
        guard let defaults = sharedDefaults else { return }
        
        let allKeys = defaults.dictionaryRepresentation().keys
        let cacheKeys = allKeys.filter { $0.hasPrefix(cacheKey) }
        
        var removedCount = 0
        
        for key in cacheKeys {
            if let data = defaults.data(forKey: key),
               let cached = try? JSONDecoder().decode(CachedAIContent.self, from: data),
               cached.expiresAt <= Date() {
                defaults.removeObject(forKey: key)
                removedCount += 1
            }
        }
        
        if removedCount > 0 {
            AppLogger.ai("Cleaned up \(removedCount) expired cache entries", level: .info)
        }
    }
}

