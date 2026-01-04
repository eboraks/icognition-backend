//
//  LibraryView.swift
//  iso-app
//
//  Main library view for displaying saved articles with search and filtering
//

import SwiftUI
import os.log
import TreePicker

/// Main library view for displaying saved articles with search and filtering
struct LibraryView: View {
    @StateObject private var contentProcessor = ContentProcessor.shared
    
    // Backend is the source of truth - fetch documents from API
    @State private var documents: [ArticleData] = []
    @State private var filteredArticles: [ArticleData] = []
    @State private var isLoading = false
    @State private var searchText = ""
    @State private var showingEntityTreeFilter = false
    @State private var selectedArticle: ArticleData?
    @State private var showingDebugFiles = false
    @State private var entityTree: EntityTreeResponse?
    @State private var selectedEntityIds: Set<Int> = []
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // App Header with Logo and User Menu
                AppHeaderView()
                
                // Custom Header "My Library" - reduced size
                HStack {
                    Text("My Library")
                        .font(.title2)
                        .fontWeight(.bold)
                    Spacer()
                }
                .padding(.horizontal)
                .padding(.top, 4)
                
                // Filter and Sort Bar
                HStack {
                    Button(action: {
                        showingEntityTreeFilter = true
                    }) {
                        VStack(spacing: 4) {
                            Text("Filter")
                                .font(.subheadline)
                                .foregroundColor(.primary)
                            Rectangle()
                                .fill(selectedEntityIds.isEmpty ? Color.clear : Color.blue)
                                .frame(height: 2)
                        }
                    }
                    
                    Spacer()
                    
                    Button(action: {
                        // Sort action
                    }) {
                        Text("Sort")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    
                    Text("Sort") // Placeholder for second sort option if needed
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .padding(.leading, 16)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
                
                Divider()
                
                // Content
                if isLoading {
                    loadingView
                } else if filteredArticles.isEmpty {
                    emptyStateView
                } else {
                    articlesList
                }
            }
            .navigationBarHidden(true) // Hide default navigation bar
            .sheet(isPresented: $showingEntityTreeFilter) {
                NavigationStack {
                    EntityTreeFilterView(
                        selectedEntityIds: $selectedEntityIds,
                        isPresented: $showingEntityTreeFilter
                    )
                }
            }
            .sheet(item: $selectedArticle) { article in
                DocumentDetailView(article: article)
            }
            .onAppear {
                Task {
                    await fetchDocumentsFromBackend()
                    await fetchEntityTree()
                }
            }
            .refreshable {
                await fetchDocumentsFromBackend()
            }
            .onChange(of: searchText) { _ in
                filterArticles()
            }
            .onChange(of: selectedEntityIds) { _ in
                filterArticles()
            }
        }
    }
    
    // MARK: - Articles List
    
    private var articlesList: some View {
        List {
            ForEach(filteredArticles, id: \.url) { article in
                ArticleCardView(article: article) {
                    AppLogger.ui("Article tapped - \(article.title)", level: .info)
                    selectedArticle = article
                }
                .listRowSeparator(.hidden)
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button("Delete") {
                        Task {
                            await deleteArticleAsync(article)
                        }
                    }
                    .tint(.red)
                }
            }
        }
        .listStyle(PlainListStyle())
        .refreshable {
            await fetchDocumentsFromBackend()
        }
    }
    
    // MARK: - Loading View
    
    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.2)
            
            Text("Loading articles...")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    // MARK: - Empty State View
    
    private var emptyStateView: some View {
        VStack(spacing: 20) {
            Image(systemName: "doc.text")
                .font(.system(size: 60))
                .foregroundColor(.secondary)
            
            VStack(spacing: 8) {
                Text("No Articles Found")
                    .font(.title2)
                    .fontWeight(.semibold)
                
                Text("Use the Share Extension to save articles and URLs")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
            
            Button("Refresh") {
                refreshContent()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    // MARK: - Helper Methods
    
    /// Fetch documents from backend API (source of truth)
    private func fetchDocumentsFromBackend() async {
        AppLogger.ui("LibraryView: Fetching documents from backend", level: .info)
        
        await MainActor.run {
            isLoading = true
        }
        
        let fetchedDocuments = await DocumentsAPIService.shared.fetchAllDocuments()
        
        await MainActor.run {
            // Convert DocumentData to ArticleData
            self.documents = fetchedDocuments.map { document in
                DocumentsAPIService.shared.convertToArticleData(document)
            }
            
            AppLogger.ui("LibraryView: Fetched \(self.documents.count) documents from backend", level: .info)
            isLoading = false
            
            // Apply filters after fetching
            filterArticles()
        }
    }
    
    /// Fetch entity tree from backend for filtering
    private func fetchEntityTree() async {
        if let treeResponse = await EntityTreeAPIService.shared.fetchEntityTree() {
            await MainActor.run {
                self.entityTree = treeResponse
            }
        }
    }
    
    private func filterArticles() {
        var filtered = documents
        
        if !searchText.isEmpty {
            filtered = filtered.filter { article in
                article.title.localizedCaseInsensitiveContains(searchText) ||
                article.domain.localizedCaseInsensitiveContains(searchText)
            }
        }
        
        // Apply entity tree filter
        if !selectedEntityIds.isEmpty {
            // Collect all document IDs from selected entities
            var documentIdsToInclude: Set<Int> = []
            
            func collectDocumentIds(from nodes: [EntityTreeNode]) {
                for node in nodes {
                    if let data = node.data, selectedEntityIds.contains(data.entityId) {
                        documentIdsToInclude.formUnion(data.documentIds)
                    }
                    if let children = node.children {
                        collectDocumentIds(from: children)
                    }
                }
            }
            
            if let tree = entityTree {
                collectDocumentIds(from: tree.tree)
            }
            
            // Filter documents by document IDs
            if !documentIdsToInclude.isEmpty {
                filtered = filtered.filter { article in
                    if let docIdString = article.backendDocumentId,
                       let docId = Int(docIdString) {
                        return documentIdsToInclude.contains(docId)
                    }
                    return false
                }
            }
        }
        
        // Apply sorting - always sort by newest first (default)
        filtered.sort { $0.savedAt > $1.savedAt }
        
        filteredArticles = filtered
    }
    
    private func refreshContent() {
        Task {
            await fetchDocumentsFromBackend()
        }
    }
    
    private func deleteArticleAsync(_ article: ArticleData) async {
        await MainActor.run {
            documents.removeAll { $0.url == article.url }
            filterArticles()
        }
    }
}

// MARK: - Article Card View (New Design)

struct ArticleCardView: View {
    let article: ArticleData
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 12) {
                // Icon
                Image(systemName: "globe")
                    .font(.system(size: 20))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .padding(.top, 2)
                
                // Content
                VStack(alignment: .leading, spacing: 6) {
                    Text(article.title)
                        .font(.headline)
                        .fontWeight(.semibold)
                        .lineLimit(2)
                        .foregroundColor(.primary)
                    
                    HStack(spacing: 6) {
                        Text("With Three Big Election Victories") // Placeholder/Subtitle
                            .font(.subheadline)
                            .foregroundColor(.blue)
                            .lineLimit(1)
                        
                        Image(systemName: "arrow.up.forward.square")
                            .font(.caption)
                            .foregroundColor(.blue)
                        
                        Text(article.domain)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    Text(article.domain) // Source name
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(.blue)
                }
            }
            .padding()
            .background(Color.white)
            .cornerRadius(8)
            .shadow(color: Color.black.opacity(0.05), radius: 2, x: 0, y: 1)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color(.systemGray5), lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        return formatter
    }
}

// MARK: - Preview

#Preview {
    LibraryView()
}
