//
//  BookmarkDataLogger.swift
//  ShareExtension
//
//  Service for logging bookmark data as JSON files for backend testing
//

import Foundation

/// Service for logging bookmark data as JSON files for backend testing
class BookmarkDataLogger {
    
    static let shared = BookmarkDataLogger()
    
    private init() {}
    
    /// Logs bookmark data as JSON file for backend testing
    /// - Parameters:
    ///   - url: The bookmark URL
    ///   - title: The bookmark title
    ///   - description: Optional description
    ///   - content: Optional full content
    ///   - metadata: Optional additional metadata
    func logBookmarkData(
        url: String,
        title: String,
        description: String? = nil,
        content: String? = nil,
        metadata: [String: Any]? = nil
    ) {
        AppLogger.shareExtension("Creating test data for backend...", level: .info)
        
        // Create the bookmark data structure matching your backend model
        let bookmarkData: [String: Any] = [
            "url": url,
            "title": title,
            "description": description as Any,
            "content": content as Any,
            "metadata": metadata as Any
        ]
        
        // Generate filename with timestamp
        let timestamp = DateFormatter.timestampFormatter.string(from: Date())
        let filename = "bookmark_\(timestamp).json"
        
        // Get Documents directory path
        guard let documentsPath = getDocumentsDirectory() else {
            AppLogger.storage("Failed to get Documents directory", level: .error)
            return
        }
        
        let fileURL = documentsPath.appendingPathComponent(filename)
        
        do {
            // Convert to JSON data
            let jsonData = try JSONSerialization.data(withJSONObject: bookmarkData, options: [.prettyPrinted, .sortedKeys])
            
            // Write to file
            try jsonData.write(to: fileURL)
            
            AppLogger.storage("Successfully created test data file: \(fileURL.path)", level: .info)
            AppLogger.storage("Data preview: \(String(data: jsonData, encoding: .utf8) ?? "Failed to convert to string")", level: .debug)
            
            // Also print the simulator path for easy access
            printSimulatorPath(fileURL: fileURL)
            
        } catch {
            AppLogger.storage("Failed to write JSON file: \(error)", level: .error)
        }
    }
    
    /// Logs bookmark data with extracted content
    /// - Parameters:
    ///   - url: The bookmark URL
    ///   - title: The bookmark title
    ///   - htmlContent: Raw HTML content or cleaned text
    ///   - description: Optional description
    func logBookmarkWithContent(
        url: String,
        title: String,
        htmlContent: String,
        description: String? = nil
    ) {
        AppLogger.shareExtension("Processing content for test data...", level: .debug)
        
        // Create metadata with extraction info
        let metadata: [String: Any] = [
            "extracted_at": DateFormatter.iso8601Formatter.string(from: Date()),
            "content_length": htmlContent.count,
            "extraction_method": "ShareExtension"
        ]
        
        // Log the bookmark data
        logBookmarkData(
            url: url,
            title: title,
            description: description,
            content: htmlContent,
            metadata: metadata
        )
    }
    
    /// Gets the Documents directory for the current app
    private func getDocumentsDirectory() -> URL? {
        let paths = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
        return paths.first
    }
    
    /// Prints the simulator path for easy file access
    private func printSimulatorPath(fileURL: URL) {
        print("🔍 Simulator File Access:")
        print("   To access this file on your Mac:")
        print("   1. Open Finder")
        print("   2. Press Cmd+Shift+G")
        print("   3. Paste this path: \(fileURL.path)")
        print("   4. Or use Terminal: open '\(fileURL.path)'")
    }
}

// MARK: - DateFormatter Extensions

extension DateFormatter {
    static let timestampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        return formatter
    }()
    
    static let iso8601Formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSZ"
        return formatter
    }()
}

