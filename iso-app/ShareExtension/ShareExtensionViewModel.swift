//
//  ShareExtensionViewModel.swift
//  ShareExtension
//
//  View model for ShareExtension with content extraction and backend integration
//
//  Metadata Extraction Strategy:
//  This extension uses LinkPresentation framework as the primary method for extracting
//  article metadata (title, description, images). LinkPresentation leverages Open Graph
//  metadata embedded in web pages, providing consistent and reliable extraction regardless
//  of JavaScript rendering, paywalls, or dynamic content loading.
//
//  Benefits:
//  - Consistent: Uses standardized Open Graph tags (og:title, og:description, og:image)
//  - Reliable: Works even with JavaScript-heavy sites and paywalled content
//  - Native: Built into iOS, used by iMessage, Mail, and other Apple apps
//  - Efficient: No need to parse HTML or handle complex JavaScript rendering
//

import Foundation
import SwiftUI
import LinkPresentation
import UniformTypeIdentifiers
import CoreData

@MainActor
class ShareExtensionViewModel: ObservableObject {
    @Published var title: String = ""
    @Published var url: URL?
    @Published var urlString: String = ""
    @Published var domainName: String = ""
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    @Published var metadata: LPLinkMetadata?
    @Published var saveSuccess: Bool = false
    @Published var saveSuccessMessage: String?
    
    
    // MARK: - Initialization
    func initialize(with extensionContext: NSExtensionContext?) async {
        AppLogger.shareExtension("Starting initialization...", level: .info)
        isLoading = true
        errorMessage = nil
        
        // Extract content directly - no authentication required
        AppLogger.shareExtension("Proceeding with content extraction...", level: .info)
        do {
            try await extractContent(from: extensionContext)
            AppLogger.shareExtension("Content extraction completed successfully", level: .info)
        } catch {
            errorMessage = error.localizedDescription
            AppLogger.shareExtension("Content extraction failed: \(error)", level: .error)
        }
        
        isLoading = false
        AppLogger.shareExtension("Initialization completed", level: .info)
    }
    
    
    // MARK: - Main Content Extraction Method
    func extractContent(from context: NSExtensionContext?) async throws {
        guard let context = context else {
            throw ShareExtensionError.noContent
        }
        
        guard let extensionItem = context.inputItems.first as? NSExtensionItem,
              let attachments = extensionItem.attachments, !attachments.isEmpty else {
            throw ShareExtensionError.noContent
        }
        
        AppLogger.shareExtension("Processing \(attachments.count) attachment(s)", level: .info)
        
        // Try to extract URL from attachments
        if let foundURL = await extractURL(from: context) {
            self.url = foundURL
            self.urlString = foundURL.absoluteString
            self.domainName = extractDomain(from: foundURL)
            
            AppLogger.shareExtension("Successfully extracted URL: \(foundURL.absoluteString)", level: .info)
            AppLogger.shareExtension("Domain: \(domainName)", level: .debug)
            
            // Fetch metadata for the URL
            await fetchMetadata(for: foundURL)
        } else {
            // Log available attachment types for debugging
            let attachmentTypes = attachments.compactMap { attachment in
                attachment.registeredTypeIdentifiers.first
            }
            AppLogger.shareExtension("Available attachment types: \(attachmentTypes)", level: .debug)
            
            throw ShareExtensionError.unsupportedContent
        }
    }
    
    // MARK: - Enhanced Content Extraction
    private func extractURL(from extensionContext: NSExtensionContext?) async -> URL? {
        guard let extensionContext = extensionContext else {
            AppLogger.shareExtension("No extension context provided", level: .error)
            return nil
        }
        
        guard let extensionItem = extensionContext.inputItems.first as? NSExtensionItem,
              let attachments = extensionItem.attachments, !attachments.isEmpty else {
            AppLogger.shareExtension("No extension items or attachments found", level: .error)
            return nil
        }
        
        // Check if the host app provided title directly in the extension item
        // This works for Safari, WSJ app, and other apps that provide metadata
        if let attributedTitle = extensionItem.attributedTitle, !attributedTitle.string.isEmpty {
            AppLogger.shareExtension("✅ Found title in extension item: \(attributedTitle.string)", level: .info)
            if self.title.isEmpty {
                self.title = attributedTitle.string
            }
        } else if let attributedContentText = extensionItem.attributedContentText, !attributedContentText.string.isEmpty {
            // Sometimes title is in contentText
            AppLogger.shareExtension("✅ Found title in extension contentText: \(attributedContentText.string)", level: .info)
            if self.title.isEmpty {
                self.title = attributedContentText.string
            }
        }
        
        // Log all available attachment types for debugging
        AppLogger.shareExtension("=== ATTACHMENT DEBUG INFO ===", level: .info)
        AppLogger.shareExtension("Total attachments: \(attachments.count)", level: .info)
        
        for (index, attachment) in attachments.enumerated() {
            let typeIdentifiers = attachment.registeredTypeIdentifiers
            AppLogger.shareExtension("Attachment \(index): \(typeIdentifiers)", level: .info)
            
            // Log additional info about each type
            for typeId in typeIdentifiers {
                AppLogger.shareExtension("  - \(typeId): \(attachment.hasItemConformingToTypeIdentifier(typeId))", level: .debug)
            }
        }
        
        // Process all attachments to find the best URL
        for (index, attachment) in attachments.enumerated() {
            // Priority 1: Direct URL items
            if attachment.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                AppLogger.shareExtension("Attachment \(index): Processing UTType.url", level: .info)
                do {
                    if let url = try await attachment.loadItem(forTypeIdentifier: UTType.url.identifier) as? URL {
                        AppLogger.shareExtension("✅ Found direct URL: \(url.absoluteString)", level: .info)
                        return url
                    }
                } catch {
                    AppLogger.shareExtension("❌ Error loading URL item: \(error.localizedDescription)", level: .error)
                    continue
                }
            }
            
            // Priority 2: Web page URLs (some apps provide metadata here)
            if attachment.hasItemConformingToTypeIdentifier(UTType.propertyList.identifier) {
                AppLogger.shareExtension("Attachment \(index): Processing UTType.propertyList", level: .info)
                do {
                    if let data = try await attachment.loadItem(forTypeIdentifier: UTType.propertyList.identifier) as? [String: Any] {
                        // Check for JavaScript preprocessing results (some apps provide metadata)
                        if let jsResults = data[NSExtensionJavaScriptPreprocessingResultsKey] as? [String: Any] {
                            // Extract URL
                            if let urlString = jsResults["URL"] as? String {
                                AppLogger.shareExtension("✅ Found web page URL: \(urlString)", level: .info)
                                
                                // Try to extract title from app's metadata if available
                                if let appTitle = jsResults["title"] as? String, !appTitle.isEmpty {
                                    AppLogger.shareExtension("✅ Found title in app metadata: \(appTitle)", level: .info)
                                    // Set title immediately if we have it
                                    if self.title.isEmpty {
                                        self.title = appTitle
                                    }
                                }
                                
                                return URL(string: urlString)
                            }
                        }
                    }
                } catch {
                    AppLogger.shareExtension("❌ Error loading property list: \(error.localizedDescription)", level: .error)
                    continue
                }
            }
            
            // Priority 3: Plain text containing URLs
            if attachment.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                AppLogger.shareExtension("Attachment \(index): Processing UTType.plainText", level: .info)
                do {
                    if let text = try await attachment.loadItem(forTypeIdentifier: UTType.plainText.identifier) as? String {
                        AppLogger.shareExtension("Processing text for URLs: \(text.prefix(100))...", level: .debug)
                        if let extractedURL = extractURLFromText(text) {
                            AppLogger.shareExtension("✅ Extracted URL from text: \(extractedURL.absoluteString)", level: .info)
                            return extractedURL
                        }
                    }
                } catch {
                    AppLogger.shareExtension("❌ Error loading text item: \(error.localizedDescription)", level: .error)
                    continue
                }
            }
            
            // Priority 4: Rich text containing URLs
            if attachment.hasItemConformingToTypeIdentifier(UTType.rtf.identifier) {
                AppLogger.shareExtension("Attachment \(index): Processing UTType.rtf", level: .info)
                do {
                    if let data = try await attachment.loadItem(forTypeIdentifier: UTType.rtf.identifier) as? Data,
                       let attributedString = try? NSAttributedString(data: data, options: [.documentType: NSAttributedString.DocumentType.rtf], documentAttributes: nil) {
                        let plainText = attributedString.string
                        AppLogger.shareExtension("Processing RTF text for URLs: \(plainText.prefix(100))...", level: .debug)
                        if let extractedURL = extractURLFromText(plainText) {
                            AppLogger.shareExtension("✅ Extracted URL from RTF: \(extractedURL.absoluteString)", level: .info)
                            return extractedURL
                        }
                    }
                } catch {
                    AppLogger.shareExtension("❌ Error loading RTF item: \(error.localizedDescription)", level: .error)
                    continue
                }
            }
        }
        
        AppLogger.shareExtension("No URLs found in any attachments", level: .warning)
        return nil
    }
    
    private func extractURLFromText(_ text: String) -> URL? {
        // First, try NSDataDetector for automatic URL detection
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        let matches = detector?.matches(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count))
        
        // Find the first valid HTTP/HTTPS URL
        for match in matches ?? [] {
            if let url = match.url, isValidWebURL(url) {
                return url
            }
        }
        
        // Fallback: Manual regex pattern for URLs that might be missed
        let urlPattern = #"https?://[^\s<>"{}|\\^`\[\]]+"#
        let regex = try? NSRegularExpression(pattern: urlPattern, options: .caseInsensitive)
        let range = NSRange(location: 0, length: text.utf16.count)
        
        if let match = regex?.firstMatch(in: text, options: [], range: range) {
            if let range = Range(match.range, in: text) {
                let urlString = String(text[range])
                if let url = URL(string: urlString), isValidWebURL(url) {
                    return url
                }
            }
        }
        
        return nil
    }
    
    private func isValidWebURL(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased() else { return false }
        guard scheme == "http" || scheme == "https" else { return false }
        guard let host = url.host, !host.isEmpty else { return false }
        
        // Basic validation for common URL patterns
        let hostPattern = #"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"#
        let hostRegex = try? NSRegularExpression(pattern: hostPattern)
        let hostRange = NSRange(location: 0, length: host.utf16.count)
        
        return hostRegex?.firstMatch(in: host, options: [], range: hostRange) != nil
    }
    
    private func extractDomain(from url: URL) -> String {
        return url.host?.replacingOccurrences(of: "www.", with: "") ?? url.absoluteString
    }
    
    // MARK: - Metadata Fetching (LinkPresentation-based)
    /// Fetch metadata using LinkPresentation framework
    /// This leverages Open Graph metadata embedded in web pages, providing consistent
    /// and reliable extraction of title, description, images, and other metadata
    /// regardless of JavaScript rendering or paywalls
    private func fetchMetadata(for url: URL) async {
        AppLogger.shareExtension("🔗 Fetching LinkPresentation metadata for: \(url.absoluteString)", level: .info)
        
        let metadataProvider = LPMetadataProvider()
        
        // Set timeout for metadata fetching (default is 30 seconds)
        // Use shorter timeout for Share Extensions to avoid blocking UI
        metadataProvider.timeout = 10.0
        
        do {
            AppLogger.shareExtension("⏳ Starting LinkPresentation metadata fetch...", level: .info)
            let fetchedMetadata = try await metadataProvider.startFetchingMetadata(for: url)
            self.metadata = fetchedMetadata
            
            AppLogger.shareExtension("✅ Successfully fetched LinkPresentation metadata", level: .info)
            
            // Log all available properties for debugging
            AppLogger.shareExtension("📊 LinkPresentation metadata properties:", level: .debug)
            AppLogger.shareExtension("   - title: \(fetchedMetadata.title ?? "nil")", level: .debug)
            AppLogger.shareExtension("   - url: \(fetchedMetadata.url?.absoluteString ?? "nil")", level: .debug)
            AppLogger.shareExtension("   - originalURL: \(fetchedMetadata.originalURL?.absoluteString ?? "nil")", level: .debug)
            AppLogger.shareExtension("   - has imageProvider: \(fetchedMetadata.imageProvider != nil)", level: .debug)
            AppLogger.shareExtension("   - has iconProvider: \(fetchedMetadata.iconProvider != nil)", level: .debug)
            
            // Try to get summary/description
            if let summary = fetchedMetadata.value(forKey: "summary") as? String {
                AppLogger.shareExtension("   - summary: \(summary.prefix(100))...", level: .debug)
            } else {
                AppLogger.shareExtension("   - summary: nil", level: .debug)
            }
            
            // Extract title from Open Graph metadata
            if let metadataTitle = fetchedMetadata.title, !metadataTitle.isEmpty {
                // Clean up common suffixes that some sites add
                let cleanedTitle = metadataTitle
                    .replacingOccurrences(of: " - WSJ", with: "")
                    .replacingOccurrences(of: " | WSJ", with: "")
                    .replacingOccurrences(of: " - The Wall Street Journal", with: "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                
                self.title = cleanedTitle
                AppLogger.shareExtension("✅ Extracted title from LinkPresentation: \(cleanedTitle)", level: .info)
            } else {
                AppLogger.shareExtension("⚠️ No title found in LinkPresentation metadata", level: .warning)
                AppLogger.shareExtension("   Attempting fallback: extracting title from URL path", level: .info)
                
                // Fallback: Try to extract a reasonable title from the URL
                let fallbackTitle = extractTitleFromURL(url)
                if !fallbackTitle.isEmpty {
                    self.title = fallbackTitle
                    AppLogger.shareExtension("✅ Using fallback title from URL: \(fallbackTitle)", level: .info)
                } else {
                    AppLogger.shareExtension("❌ Could not extract title from URL either", level: .warning)
                }
            }
            
        } catch {
            let nsError = error as NSError
            AppLogger.shareExtension("❌ Error fetching LinkPresentation metadata", level: .error)
            AppLogger.shareExtension("   Error domain: \(nsError.domain)", level: .error)
            AppLogger.shareExtension("   Error code: \(nsError.code)", level: .error)
            AppLogger.shareExtension("   Error description: \(error.localizedDescription)", level: .error)
            if let underlyingError = nsError.userInfo[NSUnderlyingErrorKey] as? NSError {
                AppLogger.shareExtension("   Underlying error: \(underlyingError.localizedDescription)", level: .error)
            }
            
            AppLogger.shareExtension("⚠️ LinkPresentation failed, attempting direct HTTP fetch fallback", level: .warning)
            
            // Fallback 1: Try direct HTTP fetch to get og:title from HTML
            if let httpTitle = await fetchTitleFromHTML(url) {
                self.title = httpTitle
                AppLogger.shareExtension("✅ Extracted title from direct HTTP fetch: \(httpTitle)", level: .info)
            } else {
                // Fallback 2: Try to extract title from URL path
                let fallbackTitle = extractTitleFromURL(url)
                if !fallbackTitle.isEmpty {
                    self.title = fallbackTitle
                    AppLogger.shareExtension("✅ Using fallback title from URL: \(fallbackTitle)", level: .info)
                } else {
                    AppLogger.shareExtension("❌ All fallbacks failed - user will need to enter title manually", level: .warning)
                }
            }
        }
    }
    
    /// Fallback: Directly fetch HTML and parse og:title meta tag
    /// This works when LinkPresentation fails and provides a reliable fallback
    private func fetchTitleFromHTML(_ url: URL) async -> String? {
        AppLogger.shareExtension("🔄 Attempting direct HTTP fetch for og:title", level: .info)
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 8.0
        request.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", forHTTPHeaderField: "User-Agent")
        request.setValue("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", forHTTPHeaderField: "Accept")
        
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            
            if let httpResponse = response as? HTTPURLResponse {
                AppLogger.shareExtension("HTTP Response Status: \(httpResponse.statusCode)", level: .debug)
                
                guard httpResponse.statusCode == 200 else {
                    AppLogger.shareExtension("❌ HTTP fetch returned status \(httpResponse.statusCode)", level: .warning)
                    return nil
                }
            }
            
            guard let htmlString = String(data: data, encoding: .utf8) else {
                AppLogger.shareExtension("❌ Failed to decode HTML as UTF-8", level: .warning)
                return nil
            }
            
            AppLogger.shareExtension("✅ Fetched HTML (\(htmlString.count) chars), parsing for og:title", level: .info)
            
            // Parse og:title using regex (simple and fast)
            // Look for: <meta property="og:title" content="...">
            let ogTitlePattern = #"<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']"#
            if let regex = try? NSRegularExpression(pattern: ogTitlePattern, options: .caseInsensitive),
               let match = regex.firstMatch(in: htmlString, options: [], range: NSRange(location: 0, length: htmlString.utf16.count)),
               match.numberOfRanges > 1,
               let range = Range(match.range(at: 1), in: htmlString) {
                let ogTitle = String(htmlString[range])
                AppLogger.shareExtension("✅ Found og:title in HTML: \(ogTitle)", level: .info)
                
                // Clean up common suffixes
                let cleanedTitle = ogTitle
                    .replacingOccurrences(of: " - WSJ", with: "")
                    .replacingOccurrences(of: " | WSJ", with: "")
                    .replacingOccurrences(of: " - The Wall Street Journal", with: "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                
                return cleanedTitle
            }
            
            // Fallback: Try article:title
            let articleTitlePattern = #"<meta\s+property=["']article:title["']\s+content=["']([^"']+)["']"#
            if let regex = try? NSRegularExpression(pattern: articleTitlePattern, options: .caseInsensitive),
               let match = regex.firstMatch(in: htmlString, options: [], range: NSRange(location: 0, length: htmlString.utf16.count)),
               match.numberOfRanges > 1,
               let range = Range(match.range(at: 1), in: htmlString) {
                let articleTitle = String(htmlString[range])
                AppLogger.shareExtension("✅ Found article:title in HTML: \(articleTitle)", level: .info)
                return articleTitle.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            
            // Fallback: Try <title> tag
            let titleTagPattern = #"<title[^>]*>([^<]+)</title>"#
            if let regex = try? NSRegularExpression(pattern: titleTagPattern, options: .caseInsensitive),
               let match = regex.firstMatch(in: htmlString, options: [], range: NSRange(location: 0, length: htmlString.utf16.count)),
               match.numberOfRanges > 1,
               let range = Range(match.range(at: 1), in: htmlString) {
                let titleTag = String(htmlString[range])
                AppLogger.shareExtension("✅ Found <title> tag in HTML: \(titleTag)", level: .info)
                
                // Clean up common suffixes
                let cleanedTitle = titleTag
                    .replacingOccurrences(of: " - WSJ", with: "")
                    .replacingOccurrences(of: " | WSJ", with: "")
                    .replacingOccurrences(of: " - The Wall Street Journal", with: "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                
                return cleanedTitle
            }
            
            AppLogger.shareExtension("❌ Could not find og:title, article:title, or <title> in HTML", level: .warning)
            return nil
            
        } catch {
            AppLogger.shareExtension("❌ Direct HTTP fetch failed: \(error.localizedDescription)", level: .warning)
            return nil
        }
    }
    
    /// Fallback method to extract a reasonable title from URL path
    /// This is used when LinkPresentation fails to fetch metadata
    private func extractTitleFromURL(_ url: URL) -> String {
        // Get the path component (e.g., "/world/americas/seizure-of-venezuelan-oil-strikes-at-the-h...")
        let path = url.path
        
        // Remove leading/trailing slashes and split by slashes
        let pathComponents = path.trimmingCharacters(in: CharacterSet(charactersIn: "/")).split(separator: "/")
        
        // Try to find the last meaningful component (usually the article slug)
        if let lastComponent = pathComponents.last, !lastComponent.isEmpty {
            // Clean up the slug: replace hyphens with spaces, capitalize words
            let cleaned = String(lastComponent)
                .replacingOccurrences(of: "-", with: " ")
                .replacingOccurrences(of: "_", with: " ")
                .split(separator: " ")
                .map { $0.capitalized }
                .joined(separator: " ")
            
            if !cleaned.isEmpty {
                return cleaned
            }
        }
        
        // If path extraction fails, return empty string
        return ""
    }
    
    // MARK: - Removed HTML-based title extraction
    // HTML extraction is unreliable for JavaScript-heavy sites and paywalled content.
    // LinkPresentation framework provides consistent Open Graph metadata extraction.
    
    // MARK: - Backend API Integration
    
    
    // MARK: - Save Functionality (No Authentication Required)
    func saveContent(with extensionContext: NSExtensionContext?) async throws {
        guard let url = url else {
            throw ShareExtensionError.noURL
        }
        
        guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ShareExtensionError.emptyTitle
        }
        
        isLoading = true
        errorMessage = nil
        
        do {
            AppLogger.shareExtension("Saving article: \(title)", level: .info)
            AppLogger.shareExtension("📋 Using LinkPresentation metadata as primary source", level: .info)
            
            // Prepare comprehensive metadata dictionary from LinkPresentation
            var metadataDict: [String: Any] = [:]
            
            // Add LinkPresentation metadata (primary source - Open Graph data)
            if let metadata = metadata {
                metadataDict["linkTitle"] = metadata.title
                metadataDict["linkURL"] = metadata.url?.absoluteString
                
                // Extract description from og:description via LinkPresentation
                if let description = metadata.value(forKey: "summary") as? String {
                    metadataDict["linkDescription"] = description
                    AppLogger.shareExtension("📝 Description from LinkPresentation: \(description.prefix(100))...", level: .debug)
                }
                
                // Extract image URL if available
                if let imageProvider = metadata.imageProvider {
                    // Try to get the image URL from the provider
                    metadataDict["linkImageURL"] = imageProvider.description
                    AppLogger.shareExtension("🖼️ Preview image available in metadata", level: .debug)
                }
                
                // Extract icon URL if available
                if let iconProvider = metadata.iconProvider {
                    metadataDict["linkIconURL"] = iconProvider.description
                    AppLogger.shareExtension("🔖 Icon available in metadata", level: .debug)
                }
            }
            
            // Optionally try to get HTML for backend processing (not for metadata extraction)
            // This is optional - backend can fetch the URL directly if needed
            let html = await getHTMLFromContext(extensionContext)
            var htmlFilePath: String?
            var hasLocalHTML = false
            
            if let html = html, html != "NOT_AVAILABLE" {
                htmlFilePath = saveHTMLToDisk(html, for: url)
                hasLocalHTML = true
                AppLogger.shareExtension("💾 Saved HTML for backend processing", level: .info)
            } else {
                AppLogger.shareExtension("ℹ️ No local HTML - backend will fetch URL directly", level: .info)
            }
            
            // Add HTML file path if available (optional)
            if let htmlFilePath = htmlFilePath {
                metadataDict["htmlFilePath"] = htmlFilePath
            }
            metadataDict["hasLocalHTML"] = hasLocalHTML
            metadataDict["contentExtraction"] = "backend" // Backend will fetch and parse content
            metadataDict["metadataSource"] = "LinkPresentation" // Indicate metadata came from LinkPresentation
            
            // Add system info (no authentication required)
            metadataDict["timestamp"] = Date().timeIntervalSince1970
            metadataDict["domainName"] = domainName
            metadataDict["isPaywalled"] = false
            metadataDict["source"] = "share_extension"
            metadataDict["version"] = "1.0"
            metadataDict["contentLength"] = html?.count ?? 0
            
            // Save directly to Core Data (shared with main app)
            let coreDataStack = CoreDataStack.shared
            let context = coreDataStack.newBackgroundContext()
            context.transactionAuthor = "shareExtension"
            
            // Capture values to avoid self capture issues in closure
            let saveUrl = url
            let saveTitle = title
            let saveDomain = domainName
            
            // Perform save operation on background context
            try await context.perform {
                // Check if article already exists
                let request: NSFetchRequest<Article> = Article.fetchRequest()
                request.predicate = NSPredicate(format: "url == %@", saveUrl.absoluteString)
                request.fetchLimit = 1
                
                let existingArticles = try? context.fetch(request)
                let article: Article
                
                if let existingArticle = existingArticles?.first {
                    // Update existing article
                    article = existingArticle
                    AppLogger.shareExtension("Updating existing article: \(saveTitle)", level: .info)
                } else {
                    // Create new article
                    article = Article(context: context)
                    article.id = UUID()
                    AppLogger.shareExtension("Creating new article: \(saveTitle)", level: .info)
                }
                
                // Update article properties
                article.url = saveUrl.absoluteString
                article.title = saveTitle
                article.domain = saveDomain
                article.content = "" // Backend will extract content from HTML file
                article.savedAt = Date()
                article.backendBookmarkId = nil
                article.backendDocumentId = nil
                article.htmlFilePath = htmlFilePath
                article.hasLocalHTML = hasLocalHTML
                
                // Set metadata
                if let description = metadataDict["linkDescription"] as? String {
                    article.metadataDescription = description
                }
                if let imageURL = metadataDict["linkImageURL"] as? String {
                    article.metadataImageURL = imageURL
                }
                
                // Save context
                try context.save()
                AppLogger.shareExtension("Article saved to Core Data successfully", level: .info)
            }
            
            // Also save to the enhanced shared content system (for backward compatibility)
            let sharedDataManager = SharedDataManager.shared
            sharedDataManager.saveSharedContent(
                title: title,
                url: url,
                metadata: metadataDict
            )
            
            AppLogger.shareExtension("Article saved successfully", level: .info)
            
            // List all saved files for debugging
            listSavedFiles()
            
            // Generate JSON test data for backend testing
            BookmarkDataLogger.shared.logBookmarkWithContent(
                url: url.absoluteString,
                title: title,
                htmlContent: html ?? "",
                description: metadataDict["linkDescription"] as? String
            )
            
            // Set success state
            saveSuccess = true
            saveSuccessMessage = "Article saved successfully!"
            
            // Auto-dismiss after a short delay
            try await Task.sleep(nanoseconds: 1_500_000_000) // 1.5 seconds
            
        } catch {
            AppLogger.shareExtension("Save failed: \(error)", level: .error)
            errorMessage = error.localizedDescription
            saveSuccess = false
            saveSuccessMessage = nil
            throw error
        }
        
        isLoading = false
    }
    
    // MARK: - Content Extraction
    
    // MARK: - Disk Storage
    
    /// Save raw HTML to App Group container
    private func saveHTMLToDisk(_ html: String, for url: URL) -> String? {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: "group.com.icognition.app"
        ) else {
            AppLogger.storage("Cannot access App Group container", level: .error)
            return nil
        }
        
        let htmlDirectory = containerURL.appendingPathComponent("html_cache")
        
        // Create directory if needed
        try? FileManager.default.createDirectory(
            at: htmlDirectory,
            withIntermediateDirectories: true
        )
        
        // Generate filename from URL and timestamp
        let filename = "\(url.host ?? "unknown")_\(Date().timeIntervalSince1970).html"
        let fileURL = htmlDirectory.appendingPathComponent(filename)
        
        do {
            try html.write(to: fileURL, atomically: true, encoding: .utf8)
            let relativePath = "html_cache/\(filename)"
            AppLogger.storage("✅ Saved HTML: \(relativePath) (\(html.count) chars)", level: .info)
            AppLogger.storage("📁 Full path: \(fileURL.path)", level: .info)
            return relativePath
        } catch {
            AppLogger.storage("❌ Failed to save HTML: \(error.localizedDescription)", level: .error)
            return nil
        }
    }
    
    /// Get HTML content from share context
    /// Safari provides URLs which we fetch using Safari's browsing context (preserves authentication/cookies)
    private func getHTMLFromContext(_ context: NSExtensionContext?) async -> String? {
        guard let context = context,
              let item = context.inputItems.first as? NSExtensionItem,
              let attachments = item.attachments else {
            AppLogger.shareExtension("No context or attachments available for HTML extraction", level: .error)
            return nil
        }
        
        AppLogger.shareExtension("=== HTML EXTRACTION DEBUG ===", level: .info)
        AppLogger.shareExtension("Processing \(attachments.count) attachments for HTML content", level: .info)
        
        // Safari typically shares content through these type identifiers
        for (index, attachment) in attachments.enumerated() {
            let typeIdentifiers = attachment.registeredTypeIdentifiers
            AppLogger.shareExtension("Attachment \(index) types: \(typeIdentifiers)", level: .info)
            
            // Priority 1: Direct HTML content (rare)
            if attachment.hasItemConformingToTypeIdentifier("public.html") {
                AppLogger.shareExtension("Attachment \(index): Found public.html", level: .info)
                do {
                    if let data = try await attachment.loadItem(forTypeIdentifier: "public.html") as? Data,
                       let htmlString = String(data: data, encoding: .utf8) {
                        AppLogger.shareExtension("✅ Retrieved HTML directly (\(htmlString.count) chars)", level: .info)
                        // Note: We rely on LinkPresentation for metadata, not HTML parsing
                        return htmlString
                    }
                } catch {
                    AppLogger.shareExtension("❌ Failed to load HTML: \(error.localizedDescription)", level: .error)
                }
            }
            
            // Priority 2: Property list with preprocessed HTML (Safari extensions)
            if attachment.hasItemConformingToTypeIdentifier("com.apple.property-list") {
                AppLogger.shareExtension("Attachment \(index): Found com.apple.property-list", level: .info)
                do {
                    if let dict = try await attachment.loadItem(forTypeIdentifier: "com.apple.property-list") as? [String: Any],
                       let results = dict["NSExtensionJavaScriptPreprocessingResultsKey"] as? [String: Any],
                       let html = results["HTML"] as? String {
                        AppLogger.shareExtension("✅ Retrieved preprocessed HTML (\(html.count) chars)", level: .info)
                        // Note: We rely on LinkPresentation for metadata, not HTML parsing
                        return html
                    }
                } catch {
                    AppLogger.shareExtension("❌ Failed to load property list: \(error.localizedDescription)", level: .error)
                }
            }
            
            // Priority 3: URL (most common) - fetch using Safari's session context
            // This preserves authentication and can access paywalled content
            if attachment.hasItemConformingToTypeIdentifier("public.url") {
                AppLogger.shareExtension("Attachment \(index): Found public.url", level: .info)
                do {
                    if let url = try await attachment.loadItem(forTypeIdentifier: "public.url") as? URL {
                        AppLogger.shareExtension("Attempting to fetch HTML from URL: \(url.absoluteString)", level: .info)
                        
                        // Try with custom User-Agent to mimic Safari
                        var request = URLRequest(url: url)
                        request.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", forHTTPHeaderField: "User-Agent")
                        request.setValue("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", forHTTPHeaderField: "Accept")
                        request.setValue("en-US,en;q=0.5", forHTTPHeaderField: "Accept-Language")
                        
                        let (data, response) = try await URLSession.shared.data(for: request)
                        
                        if let httpResponse = response as? HTTPURLResponse {
                            AppLogger.shareExtension("HTTP Response Status: \(httpResponse.statusCode)", level: .info)
                            AppLogger.shareExtension("Response Headers: \(httpResponse.allHeaderFields)", level: .debug)
                        }
                        
                        if let htmlContent = String(data: data, encoding: .utf8) {
                            AppLogger.shareExtension("✅ Fetched HTML from URL (\(htmlContent.count) chars)", level: .info)
                            
                            // Note: We rely on LinkPresentation for metadata extraction, not HTML parsing
                            // HTML is saved for backend processing, but metadata comes from LinkPresentation
                            
                            // Check if this looks like LinkedIn guest content
                            if htmlContent.contains("data-member-id=\"0\"") || htmlContent.contains("guest-frontend") {
                                AppLogger.shareExtension("⚠️ LinkedIn guest content detected - limited access", level: .warning)
                                AppLogger.shareExtension("📝 Will save URL and metadata, but HTML content is limited", level: .info)
                                return "NOT_AVAILABLE"
                            }
                            
                            return htmlContent
                        } else {
                            AppLogger.shareExtension("❌ Failed to decode HTML from URL", level: .error)
                        }
                    }
                } catch {
                    AppLogger.shareExtension("❌ Failed to load URL: \(error.localizedDescription)", level: .error)
                }
            }
        }
        
        AppLogger.shareExtension("❌ No HTML content available from any attachment", level: .warning)
        return nil
    }
    
    
    // MARK: - Debug Methods
    
    /// List all saved HTML files for debugging
    func listSavedFiles() {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: "group.com.icognition.app"
        ) else {
            AppLogger.storage("Cannot access App Group container for file listing", level: .error)
            return
        }
        
        let htmlDirectory = containerURL.appendingPathComponent("html_cache")
        
        do {
            let files = try FileManager.default.contentsOfDirectory(at: htmlDirectory, includingPropertiesForKeys: [.fileSizeKey, .creationDateKey])
            AppLogger.storage("📁 Found \(files.count) HTML files:", level: .info)
            
            for file in files {
                let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
                let fileSize = attributes[.size] as? Int64 ?? 0
                let creationDate = attributes[.creationDate] as? Date ?? Date()
                let formatter = DateFormatter()
                formatter.dateStyle = .short
                formatter.timeStyle = .short
                
                AppLogger.storage("  - \(file.lastPathComponent) (\(fileSize) bytes, \(formatter.string(from: creationDate)))", level: .info)
            }
        } catch {
            AppLogger.storage("Failed to list HTML files: \(error.localizedDescription)", level: .error)
        }
    }
    
    // MARK: - Validation
    var canSave: Bool {
        return url != nil && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isLoading
    }
    
    func clearError() {
        errorMessage = nil
        saveSuccess = false
        saveSuccessMessage = nil
    }
    
    
    // MARK: - Cancel Functionality
    func cancel() {
        // Clear any pending state
        clearError()
        isLoading = false
    }
}

// MARK: - Custom Errors
enum ShareExtensionError: LocalizedError {
    case noURL
    case emptyTitle
    case saveFailed(String)
    case noContent
    case unsupportedContent
    case invalidURL(String)
    case extractionFailed(String)
    case invalidResponse
    case httpError(Int)
    case invalidData
    
    var errorDescription: String? {
        switch self {
        case .noURL:
            return "No URL found in shared content"
        case .emptyTitle:
            return "Please enter a title for this article"
        case .saveFailed(let message):
            return "Failed to save: \(message)"
        case .noContent:
            return "No content found to share"
        case .unsupportedContent:
            return "This type of content is not supported"
        case .invalidURL(let urlString):
            return "Invalid URL format: \(urlString)"
        case .extractionFailed(let reason):
            return "Failed to extract content: \(reason)"
        case .invalidResponse:
            return "Invalid response from server"
        case .httpError(let code):
            return "HTTP error: \(code)"
        case .invalidData:
            return "Invalid data received"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .noURL, .noContent:
            return "Please share a webpage or text containing a URL"
        case .emptyTitle:
            return "Enter a descriptive title for this article"
        case .unsupportedContent:
            return "Try sharing from a web browser or text containing a URL"
        case .invalidURL:
            return "Please check that the URL is properly formatted"
        case .saveFailed, .extractionFailed:
            return "Please try again or contact support if the problem persists"
        case .invalidResponse, .httpError, .invalidData:
            return "Please check your internet connection and try again"
        }
    }
}

