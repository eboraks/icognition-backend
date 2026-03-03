//
//  DocumentDetailView.swift
//  iso-app
//
//  Detailed view for a single document with tabs for key points, chat, and source
//

import SwiftUI
import WebKit
import os.log

// MARK: - Document Tab Enum

enum DocumentTab: String, CaseIterable {
    case keyPoints = "Key Points"
    case chat = "Chat"
    case source = "Source"
}

// MARK: - Document Detail View

struct DocumentDetailView: View {
    let article: ArticleData
    @Environment(\.presentationMode) var presentationMode
    @State private var isLoading = true
    @State private var articleContent: String = ""
    @State private var errorMessage: String?
    @State private var showingError = false
    
    // Chat
    @StateObject private var chatStore = ChatStore()
    @State private var activeChatSession: ICChatSession?
    
    // AI content from backend
    @State private var aiMarkdownContent: String?
    
    // Tab selection
    @State private var selectedTab: DocumentTab = .keyPoints
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Article header
                articleHeaderView
                
                // Tab selector
                tabSelectorView
                
                // Tab content
                tabContentView
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack {
                        // AI Refresh Button
                        Button(action: {
                            Task {
                                await refreshAIContent()
                            }
                        }) {
                            Image(systemName: "sparkles")
                        }
                        
                        Button("Done") {
                            presentationMode.wrappedValue.dismiss()
                        }
                    }
                }
            }
            .onAppear {
                Task {
                    await loadArticleContent()
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .aiContentReady)) { notification in
                // Check if this notification is for our article
                if let documentId = notification.userInfo?["documentId"] as? String,
                   documentId == article.backendDocumentId {
                    AppLogger.ui("AI content ready for current article, refreshing...", level: .info)
                    Task {
                        await loadArticleContent()
                    }
                }
            }
            .alert("Error", isPresented: $showingError) {
                Button("OK") { }
            } message: {
                Text(errorMessage ?? "Unknown error occurred")
            }
        }
    }
    
    // MARK: - Tabbed Interface Views
    
    private var articleHeaderView: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Article title
            Text(article.title)
                .font(.title2)
                .fontWeight(.bold)
                .multilineTextAlignment(.leading)
            
            // Article metadata
            HStack {
                Image(systemName: "newspaper")
                    .foregroundColor(.secondary)
                    .font(.caption)
                
                Text(article.domain)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Text("•")
                    .foregroundColor(.secondary)
                
                Text(article.savedAt, formatter: dateFormatter)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            
            // Author info (if available)
            if let metadata = article.metadata, let author = metadata.author {
                HStack {
                    Image(systemName: "person.circle")
                        .foregroundColor(.secondary)
                        .font(.caption)
                    
                    Text("By \(author)")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
    }
    
    private var tabSelectorView: some View {
        HStack(spacing: 0) {
            ForEach(DocumentTab.allCases, id: \.self) { tab in
                Button(action: {
                    selectedTab = tab
                }) {
                    VStack(spacing: 4) {
                        Text(tab.rawValue)
                            .font(.subheadline)
                            .fontWeight(selectedTab == tab ? .semibold : .regular)
                            .foregroundColor(selectedTab == tab ? .primary : .secondary)
                        
                        Rectangle()
                            .fill(selectedTab == tab ? Color.primary : Color.clear)
                            .frame(height: 2)
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.horizontal)
        .background(Color(.systemBackground))
    }
    
    private var tabContentView: some View {
        Group {
            switch selectedTab {
            case .keyPoints:
                keyPointsView
            case .chat:
                chatView
            case .source:
                sourceView
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var keyPointsView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if isLoading {
                    VStack(spacing: 16) {
                        ProgressView()
                            .scaleEffect(1.2)
                        Text("Loading AI insights...")
                            .font(.headline)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    // AI analysis section
                    if let markdown = aiMarkdownContent, !markdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Image(systemName: "text.alignleft")
                                    .foregroundColor(.blue)
                                Text("AI Analysis")
                                    .font(.headline)
                                    .foregroundColor(.blue)
                            }

                            Text(LocalizedStringKey(markdown))
                                .font(.body)
                                .multilineTextAlignment(.leading)
                                .padding()
                                .background(Color.blue.opacity(0.1))
                                .cornerRadius(12)
                        }
                    }

                    // Empty state if no AI content
                    if aiMarkdownContent == nil || aiMarkdownContent!.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        VStack(spacing: 16) {
                            Image(systemName: "brain.head.profile")
                                .font(.system(size: 48))
                                .foregroundColor(.secondary)
                            
                            Text("No AI insights available")
                                .font(.headline)
                                .foregroundColor(.secondary)
                            
                            Text("AI processing may still be in progress, or this document doesn't have AI-generated content yet.")
                                .font(.body)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .padding()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            }
            .padding()
        }
    }
    
    private var chatView: some View {
        Group {
            if let session = activeChatSession {
                SessionChatView(session: session, store: chatStore)
            } else {
                VStack(spacing: 16) {
                    if chatStore.isLoading {
                        ProgressView()
                            .scaleEffect(1.2)
                    } else {
                        Image(systemName: "message.circle")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        
                        Text("Start Chat")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        
                        Text("Chat with this document using AI.")
                            .font(.body)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                        
                        Button(action: {
                            Task {
                                await startChat()
                            }
                        }) {
                            Text("Start Conversation")
                                .fontWeight(.semibold)
                                .foregroundColor(.white)
                                .padding(.horizontal, 24)
                                .padding(.vertical, 12)
                                .background(Color.blue)
                                .cornerRadius(24)
                        }
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            if selectedTab == .chat && activeChatSession == nil && !chatStore.isLoading {
                Task {
                    await startChat()
                }
            }
        }
    }
    
    private var sourceView: some View {
        Group {
            if isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.2)
                    Text("Loading document content...")
                        .font(.headline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if !articleContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                HTMLContentView(htmlContent: articleContent)
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "doc.text")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    
                    Text("Content Not Available")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    
                    Text("This document doesn't have content available. The content may be processing or unavailable.")
                        .font(.body)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }
    
    
    // MARK: - Helper Methods
    
    private func startChat() async {
        guard let documentIdString = article.backendDocumentId,
              let documentId = Int(documentIdString) else {
            // Cannot start chat without document ID
            AppLogger.ui("Cannot start chat: No valid backend document ID", level: .warning)
            return
        }
        
        if let session = await chatStore.getOrCreateSession(
            scopeType: .document,
            scopeId: documentId,
            title: article.title
        ) {
            await MainActor.run {
                self.activeChatSession = session
            }
        }
    }
    
    private func refreshAIContent() async {
        isLoading = true
        
        // Fetch fresh document from backend using document ID
        if let documentId = article.backendDocumentId {
            AppLogger.ui("Refreshing document content for document: \(documentId)", level: .info)
            
            if let documentData = await DocumentAPIService.shared.fetchDocument(documentId: documentId) {
                // Update AI content
                await updateArticleWithAIContent(markdownContent: documentData.aiMarkdownContent)

                // Update content
                if let content = documentData.content, !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    await MainActor.run {
                        self.articleContent = content
                    }
                }
                
                AppLogger.ui("Successfully refreshed document content", level: .info)
            } else {
                AppLogger.ui("Failed to fetch fresh document data", level: .error)
                errorMessage = "Failed to refresh document content. Please try again."
                showingError = true
            }
        } else {
            AppLogger.ui("No document ID available for refresh", level: .warning)
            errorMessage = "No document ID available. Please ensure the document has been synced with the backend."
            showingError = true
        }
        
        isLoading = false
    }
    
    private func loadArticleContent() async {
        AppLogger.ui("Starting to load document content...", level: .info)
        AppLogger.ui("Document has backendDocumentId: \(article.backendDocumentId ?? "nil")", level: .info)
        AppLogger.ui("Document has backendBookmarkId: \(article.backendBookmarkId ?? "nil")", level: .info)
        
        isLoading = true
        errorMessage = nil
        
        // Fetch document from backend using document ID (source of truth)
        if let documentId = article.backendDocumentId {
            AppLogger.ui("Fetching document from backend: \(documentId)", level: .info)
            
            if let documentData = await DocumentAPIService.shared.fetchDocument(documentId: documentId) {
                AppLogger.ui("Successfully fetched document from backend", level: .info)
                
                // Update AI content from backend
                await updateArticleWithAIContent(markdownContent: documentData.aiMarkdownContent)
                
                // Use content from backend document (source of truth)
                if let backendContent = documentData.content, !backendContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    AppLogger.ui("Using backend document content (\(backendContent.count) characters)", level: .info)
                    
                    await MainActor.run {
                        self.articleContent = backendContent
                        self.isLoading = false
                    }
                } else {
                    AppLogger.ui("Backend document has no content", level: .warning)
                    await MainActor.run {
                        self.articleContent = ""
                        self.isLoading = false
                    }
                }
            } else {
                AppLogger.ui("Failed to fetch document from backend", level: .error)
                errorMessage = "Failed to load document content. Please try again."
                showingError = true
                
                // Fallback to article content if available
                if let articleContent = article.content, !articleContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    await MainActor.run {
                        self.articleContent = articleContent
                        self.isLoading = false
                    }
                } else {
                    await MainActor.run {
                        self.articleContent = ""
                        self.isLoading = false
                    }
                }
            }
        } else {
            AppLogger.ui("No backend document ID found, using article data", level: .warning)
            
            // Fallback: Use AI content from article if available
            if let markdown = article.aiMarkdownContent, !markdown.isEmpty {
                AppLogger.ui("Using AI content from article data", level: .info)
                await updateArticleWithAIContent(markdownContent: markdown)
            }
            
            // Use content from article
            if let articleContent = article.content, !articleContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                await MainActor.run {
                    self.articleContent = articleContent
                    self.isLoading = false
                }
            } else {
                await MainActor.run {
                    self.articleContent = ""
                    self.isLoading = false
                }
            }
        }
    }
    
    /// Updates the article with AI content
    private func updateArticleWithAIContent(markdownContent: String?) async {
        AppLogger.ui("Updating article with AI content...", level: .info)

        await MainActor.run {
            self.aiMarkdownContent = markdownContent
            AppLogger.ui("AI Markdown content set: \(markdownContent != nil)", level: .debug)
        }
    }
    
    private var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        return formatter
    }
}

// MARK: - HTML Content View

struct HTMLContentView: UIViewRepresentable {
    let htmlContent: String
    
    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        return webView
    }
    
    func updateUIView(_ webView: WKWebView, context: Context) {
        // Load HTML content
        let htmlString = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    color: #333;
                    padding: 16px;
                    max-width: 100%;
                    word-wrap: break-word;
                }
                img {
                    max-width: 100%;
                    height: auto;
                }
                a {
                    color: #007AFF;
                    text-decoration: none;
                }
                pre {
                    background-color: #f5f5f5;
                    padding: 12px;
                    border-radius: 4px;
                    overflow-x: auto;
                }
                code {
                    background-color: #f5f5f5;
                    padding: 2px 4px;
                    border-radius: 2px;
                }
            </style>
        </head>
        <body>
        \(htmlContent)
        </body>
        </html>
        """
        webView.loadHTMLString(htmlString, baseURL: nil)
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Allow navigation within the same page, but open external links in Safari
            if navigationAction.navigationType == .linkActivated {
                if let url = navigationAction.request.url {
                    UIApplication.shared.open(url)
                    decisionHandler(.cancel)
                    return
                }
            }
            decisionHandler(.allow)
        }
    }
}

// MARK: - Document Errors

enum DocumentError: LocalizedError {
    case invalidURL
    case invalidResponse
    case invalidData
    case httpError(Int)
    case networkError
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid document URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .invalidData:
            return "Invalid data received"
        case .httpError(let code):
            return "HTTP error: \(code)"
        case .networkError:
            return "Network connection error"
        }
    }
}

// MARK: - Preview

#Preview {
    DocumentDetailView(article: ArticleData(
        url: "https://example.com/article",
        title: "Sample Document",
        domain: "example.com",
        content: "This is a sample document content.",
        metadata: ArticleMetadata(description: "A sample document for preview")
    ))
}

