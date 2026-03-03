//
//  DocumentPollingService.swift
//  iso-app
//
//  Service to poll for document processing completion and AI content availability
//

import Foundation
import os.log

/// Service to poll for document processing completion
class DocumentPollingService {
    static let shared = DocumentPollingService()
    
    private let logger = Logger(subsystem: "com.icognition.iso-app", category: "DocumentPollingService")
    private let documentAPIService = DocumentAPIService.shared
    private let aiContentCacheService = AIContentCacheService.shared
    
    // Track active polling tasks
    private var activePollingTasks: [String: Task<Void, Never>] = [:]
    
    private init() {}
    
    /// Start polling for document processing completion
    /// - Parameters:
    ///   - documentId: The document ID to poll for
    ///   - maxAttempts: Maximum number of polling attempts (default: 60 = 5 minutes)
    ///   - intervalSeconds: Polling interval in seconds (default: 5)
    func startPolling(
        documentId: String,
        maxAttempts: Int = 60,
        intervalSeconds: TimeInterval = 5.0
    ) {
        // Stop any existing polling for this document
        stopPolling(documentId: documentId)
        
        AppLogger.ai("Starting polling for document \(documentId)", level: .info)
        
        let task = Task {
            await pollForCompletion(
                documentId: documentId,
                maxAttempts: maxAttempts,
                intervalSeconds: intervalSeconds
            )
        }
        
        activePollingTasks[documentId] = task
    }
    
    /// Stop polling for a specific document
    func stopPolling(documentId: String) {
        if let task = activePollingTasks[documentId] {
            task.cancel()
            activePollingTasks.removeValue(forKey: documentId)
            AppLogger.ai("Stopped polling for document \(documentId)", level: .info)
        }
    }
    
    /// Stop all active polling
    func stopAllPolling() {
        for (documentId, task) in activePollingTasks {
            task.cancel()
            AppLogger.ai("Stopped polling for document \(documentId)", level: .info)
        }
        activePollingTasks.removeAll()
    }
    
    // MARK: - Private Methods
    
    private func pollForCompletion(
        documentId: String,
        maxAttempts: Int,
        intervalSeconds: TimeInterval
    ) async {
        var attempts = 0
        
        while attempts < maxAttempts && !Task.isCancelled {
            attempts += 1
            
            AppLogger.ai("Polling attempt \(attempts)/\(maxAttempts) for document \(documentId)", level: .debug)
            
            do {
                // Fetch document data
                if let documentData = await documentAPIService.fetchDocument(documentId: documentId) {
                    
                    // Check if AI content is available
                    let hasMarkdown = documentData.aiMarkdownContent != nil && !documentData.aiMarkdownContent!.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty

                    if hasMarkdown {
                        AppLogger.ai("✅ AI content available for document \(documentId)", level: .info)
                        
                        // Cache the AI content
                        await aiContentCacheService.prefetchAndCache(documentId: documentId)
                        
                        // Post notification that AI content is ready
                        NotificationCenter.default.post(
                            name: NSNotification.Name("AIContentReady"),
                            object: nil,
                            userInfo: ["documentId": documentId]
                        )
                        
                        // Stop polling for this document
                        stopPolling(documentId: documentId)
                        return
                        
                    } else {
                        AppLogger.ai("⏳ AI content not ready yet for document \(documentId) (attempt \(attempts))", level: .debug)
                    }
                    
                } else {
                    AppLogger.ai("❌ Failed to fetch document \(documentId) (attempt \(attempts))", level: .warning)
                }
                
            } catch {
                AppLogger.ai("❌ Error polling document \(documentId): \(error.localizedDescription)", level: .error)
            }
            
            // Wait before next attempt
            if attempts < maxAttempts && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(intervalSeconds * 1_000_000_000))
            }
        }
        
        if attempts >= maxAttempts {
            AppLogger.ai("⏰ Polling timeout for document \(documentId) after \(maxAttempts) attempts", level: .warning)
            
            // Post notification that polling timed out
            NotificationCenter.default.post(
                name: NSNotification.Name("AIContentTimeout"),
                object: nil,
                userInfo: ["documentId": documentId]
            )
        }
        
        // Clean up
        activePollingTasks.removeValue(forKey: documentId)
    }
}

// MARK: - Notification Names

extension NSNotification.Name {
    static let aiContentReady = NSNotification.Name("AIContentReady")
    static let aiContentTimeout = NSNotification.Name("AIContentTimeout")
}
