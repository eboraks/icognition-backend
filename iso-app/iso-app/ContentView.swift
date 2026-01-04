//
//  ContentView.swift
//  iso-app
//
//  Main app view with authentication and tabs
//

import SwiftUI
import FirebaseAuth
import os.log

struct ContentView: View {
    @StateObject private var googleAuthManager = AuthenticationManager()
    @StateObject private var appleAuthManager = AppleAuthManager()
    @StateObject private var contentManager = ContentManager.shared
    
    @State private var selectedTab = 0
    
    // Use whichever auth manager has an authenticated user
    private var isAuthenticated: Bool {
        return googleAuthManager.isAuthenticated || appleAuthManager.isAuthenticated
    }
    
    private var currentUser: User? {
        return googleAuthManager.currentUser ?? appleAuthManager.currentUser
    }
    
    var body: some View {
        if isAuthenticated {
            // Main app interface with tabs
            TabView(selection: $selectedTab) {
                // Library Tab (previously Home)
                LibraryView()
                    .tabItem {
                        Image(systemName: "books.vertical")
                        Text("Library")
                    }
                    .tag(0)
                
                // Q&A Tab
                ChatSessionListView()
                    .tabItem {
                        Image(systemName: "message")
                        Text("Q&A")
                    }
                    .tag(1)
                
                // Explorer Tab (Placeholder for now, reuse HomeView logic or create new)
                NavigationView {
                    Text("Explorer Coming Soon")
                        .navigationTitle("Explorer")
                }
                .tabItem {
                    Image(systemName: "safari")
                    Text("Explorer")
                }
                .tag(2)
                
                // Settings Tab
                SettingsView()
                    .tabItem {
                        Image(systemName: "gearshape")
                        Text("Settings")
                    }
                    .tag(3)
            }
            .onReceive(NotificationCenter.default.publisher(for: .contentDidUpdate)) { _ in
                contentManager.loadArticles()
            }
            .onReceive(NotificationCenter.default.publisher(for: NSNotification.Name("OpenLibraryFromShareExtension"))) { notification in
                AppLogger.ui("Received OpenLibraryFromShareExtension notification", level: .info)
                selectedTab = 0 // Navigate to Library tab
            }
            .onAppear {
                // Start monitoring for new content from ShareExtension
                AppLogger.main("Starting ContentProcessor monitoring", level: .info)
                ContentProcessor.shared.startMonitoring()
            }
        } else {
            // Show authentication view with shared auth managers
            AuthenticationView()
                .environmentObject(googleAuthManager)
                .environmentObject(appleAuthManager)
        }
    }
}

// MARK: - Preview

#Preview {
    ContentView()
}
