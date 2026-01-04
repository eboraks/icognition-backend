//
//  ChatSessionListView.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import SwiftUI

struct ChatSessionListView: View {
    @StateObject private var store = ChatStore()
    @State private var selectedSession: ICChatSession?
    @State private var isCreatingChat = false
    @State private var editingSession: ICChatSession?
    @State private var editingTitle: String = ""
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // App Header with Logo and User Menu - at the very top
                AppHeaderView()
                
                // Custom header with title and + button
                HStack {
                    Text("Chats")
                        .font(.title2)
                        .fontWeight(.bold)
                        .padding(.leading)
                    
                    Spacer()
                    
                    Button(action: {
                        Task {
                            await createAndNavigateToNewChat()
                        }
                    }) {
                        if isCreatingChat {
                            ProgressView()
                        } else {
                            Image(systemName: "plus")
                                .foregroundColor(.blue)
                        }
                    }
                    .disabled(isCreatingChat)
                    .padding(.trailing)
                }
                .padding(.vertical, 8)
                
                // Chat List
                List {
                    if store.isLoading && store.sessions.isEmpty {
                        HStack {
                            Spacer()
                            ProgressView()
                                .padding()
                            Spacer()
                        }
                    } else if store.sessions.isEmpty {
                        Text("No chat sessions")
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding()
                    } else {
                        ForEach(store.sessions) { session in
                            NavigationLink(
                                destination: SessionChatView(session: session, store: store),
                                tag: session,
                                selection: $selectedSession
                            ) {
                                SessionRowView(
                                    session: session,
                                    isEditing: editingSession?.id == session.id,
                                    editingTitle: $editingTitle,
                                    onDoubleTap: {
                                        startEditing(session)
                                    },
                                    onSave: {
                                        Task {
                                            await saveTitle(for: session)
                                        }
                                    },
                                    onCancel: {
                                        cancelEditing()
                                    }
                                )
                            }
                        }
                        .onDelete(perform: deleteSession)
                    }
                }
                .navigationBarHidden(true)
                .refreshable {
                    await store.loadSessions()
                }
            }
            .onAppear {
                // Reload sessions when view appears
                Task {
                    await store.loadSessions()
                }
            }
        }
    }
    
    private func createAndNavigateToNewChat() async {
        isCreatingChat = true
        defer { isCreatingChat = false }
        
        if let newSession = await store.createSessionAndReturn() {
            // Small delay to ensure session is in the list
            try? await Task.sleep(nanoseconds: 100_000_000) // 0.1 seconds
            selectedSession = newSession
        }
    }
    
    private func deleteSession(at offsets: IndexSet) {
        for index in offsets {
            let session = store.sessions[index]
            Task {
                await store.deleteSession(session)
            }
        }
    }
    
    private func startEditing(_ session: ICChatSession) {
        editingSession = session
        editingTitle = session.title
    }
    
    private func saveTitle(for session: ICChatSession) async {
        guard !editingTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            cancelEditing()
            return
        }
        
        await store.updateSessionTitle(session, newTitle: editingTitle)
        editingSession = nil
        editingTitle = ""
    }
    
    private func cancelEditing() {
        editingSession = nil
        editingTitle = ""
    }
}

struct SessionRowView: View {
    let session: ICChatSession
    let isEditing: Bool
    @Binding var editingTitle: String
    let onDoubleTap: () -> Void
    let onSave: () -> Void
    let onCancel: () -> Void
    
    @FocusState private var isFocused: Bool
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if isEditing {
                HStack {
                    TextField("Session name", text: $editingTitle, onCommit: {
                        onSave()
                    })
                    .focused($isFocused)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .font(.headline)
                    
                    Button("Cancel") {
                        onCancel()
                    }
                    .font(.caption)
                    .foregroundColor(.red)
                }
                .onAppear {
                    isFocused = true
                }
            } else {
                Text(session.title)
                    .font(.headline)
                    .foregroundColor(.primary)
                    .onTapGesture(count: 2) {
                        onDoubleTap()
                    }
            }
            
            Text(session.updatedAt, style: .relative)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 4)
    }
}

