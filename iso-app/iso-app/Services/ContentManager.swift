//
//  ContentManager.swift
//  iso-app
//
//  Manages content integration between Share Extension and main app
//

import Foundation
import Combine
import UIKit

/// Manages content integration between Share Extension and main app
@MainActor
class ContentManager: ObservableObject {
    static let shared = ContentManager()
    
    @Published var articles: [ArticleData] = []
    @Published var isLoading = false
    @Published var lastUpdate: Date?
    @Published var errorMessage: String?
    
    private let sharedDataManager = SharedDataManager.shared
    private let contentProcessor = ContentProcessor.shared
    private var cancellables = Set<AnyCancellable>()
    
    private init() {
        setupObservers()
        loadArticles()
    }
    
    // MARK: - Setup
    
    private func setupObservers() {
        // Listen for content processing completion
        NotificationCenter.default.publisher(for: .contentProcessingCompleted)
            .sink { [weak self] _ in
                self?.loadArticles()
            }
            .store(in: &cancellables)
        
        // Listen for content updates
        NotificationCenter.default.publisher(for: .contentDidUpdate)
            .sink { [weak self] _ in
                self?.loadArticles()
            }
            .store(in: &cancellables)
        
        // Listen for app lifecycle events
        NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)
            .sink { [weak self] _ in
                self?.handleAppBecameActive()
            }
            .store(in: &cancellables)
    }
    
    // MARK: - Content Management
    
    /// Load all articles from storage
    func loadArticles() {
        isLoading = true
        errorMessage = nil
        
        Task {
            let loadedArticles = sharedDataManager.getAllSavedArticles()
            
            await MainActor.run {
                self.articles = loadedArticles
                self.lastUpdate = Date()
                self.isLoading = false
            }
            
            AppLogger.content("Loaded \(loadedArticles.count) articles", level: .info)
        }
    }
    
    /// Refresh content from Share Extension
    func refreshContent() {
        AppLogger.content("Refreshing content from Share Extension", level: .info)
        contentProcessor.refreshPendingContent()
        loadArticles()
    }
    
    /// Handle app becoming active
    private func handleAppBecameActive() {
        AppLogger.content("App became active - refreshing content", level: .info)
        refreshContent()
    }
    
    // MARK: - Article Operations
    
    /// Get article by URL
    func getArticle(url: String) -> ArticleData? {
        return articles.first { $0.url == url }
    }
    
    /// Get articles by domain
    func getArticles(domain: String) -> [ArticleData] {
        return articles.filter { $0.domain == domain }
    }
    
    /// Search articles
    func searchArticles(query: String) -> [ArticleData] {
        guard !query.isEmpty else { return articles }
        
        return articles.filter { article in
            article.title.localizedCaseInsensitiveContains(query) ||
            article.url.localizedCaseInsensitiveContains(query) ||
            article.domain.localizedCaseInsensitiveContains(query) ||
            article.metadata?.description?.localizedCaseInsensitiveContains(query) == true
        }
    }
    
    /// Get recent articles (last 7 days)
    func getRecentArticles() -> [ArticleData] {
        let oneWeekAgo = Date().addingTimeInterval(-7 * 24 * 60 * 60)
        return articles.filter { $0.savedAt > oneWeekAgo }
    }
    
    /// Get articles by date range
    func getArticles(from startDate: Date, to endDate: Date) -> [ArticleData] {
        return articles.filter { article in
            article.savedAt >= startDate && article.savedAt <= endDate
        }
    }
    
    // MARK: - Statistics
    
    /// Get content statistics
    func getContentStats() -> ContentStats {
        let totalArticles = articles.count
        let recentArticles = getRecentArticles().count
        let uniqueDomains = Set(articles.map { $0.domain }).count
        
        return ContentStats(
            totalArticles: totalArticles,
            recentArticles: recentArticles,
            uniqueDomains: uniqueDomains,
            lastUpdate: lastUpdate
        )
    }
    
    /// Get domain statistics
    func getDomainStats() -> [DomainStats] {
        let domainCounts = Dictionary(grouping: articles, by: { $0.domain })
            .mapValues { $0.count }
        
        return domainCounts.map { domain, count in
            DomainStats(domain: domain, count: count)
        }.sorted { $0.count > $1.count }
    }
    
    // MARK: - Error Handling
    
    /// Clear error message
    func clearError() {
        errorMessage = nil
    }
    
    /// Handle errors
    func handleError(_ error: Error) {
        errorMessage = error.localizedDescription
        AppLogger.content("ContentManager error: \(error)", level: .error)
    }
}

// MARK: - Content Manager Extensions

extension ContentManager {
    
    /// Get articles sorted by date
    func getArticlesSortedByDate(ascending: Bool = false) -> [ArticleData] {
        return articles.sorted { ascending ? $0.savedAt < $1.savedAt : $0.savedAt > $1.savedAt }
    }
    
    /// Get articles sorted by title
    func getArticlesSortedByTitle(ascending: Bool = true) -> [ArticleData] {
        return articles.sorted { ascending ? $0.title < $1.title : $0.title > $1.title }
    }
    
    /// Get articles sorted by domain
    func getArticlesSortedByDomain(ascending: Bool = true) -> [ArticleData] {
        return articles.sorted { ascending ? $0.domain < $1.domain : $0.domain > $1.domain }
    }
    
    /// Get unique domains
    func getUniqueDomains() -> [String] {
        return Array(Set(articles.map { $0.domain })).sorted()
    }
    
    /// Check if article exists
    func articleExists(url: String) -> Bool {
        return articles.contains { $0.url == url }
    }
    
    /// Get article count by domain
    func getArticleCount(for domain: String) -> Int {
        return articles.filter { $0.domain == domain }.count
    }
}

// MARK: - Content Manager Utilities

extension ContentManager {
    
    /// Export articles to JSON
    func exportArticles() -> Data? {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            encoder.outputFormatting = .prettyPrinted
            return try encoder.encode(articles)
        } catch {
            handleError(error)
            return nil
        }
    }
    
    /// Import articles from JSON
    func importArticles(from data: Data) -> Bool {
        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            let importedArticles = try decoder.decode([ArticleData].self, from: data)
            
            // Merge with existing articles
            for article in importedArticles {
                if !articleExists(url: article.url) {
                    sharedDataManager.saveArticleData(article)
                }
            }
            
            loadArticles()
            return true
        } catch {
            handleError(error)
            return false
        }
    }
    
    /// Clear all articles
    func clearAllArticles() {
        sharedDataManager.clearPendingData()
        articles = []
        lastUpdate = Date()
    }
    
    /// Get processing status
    func getProcessingStatus() -> ProcessingStatus {
        let stats = contentProcessor.getProcessingStats()
        return ProcessingStatus(
            isProcessing: stats.isProcessing,
            processedCount: stats.processedCount,
            lastProcessedAt: stats.lastProcessedAt
        )
    }
}

