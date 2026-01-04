//
//  ChatStore.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import Foundation
import Combine

@MainActor
class ChatStore: ObservableObject {
    @Published var sessions: [ICChatSession] = []
    @Published var activeSession: ICChatSession?
    @Published var messages: [ICChatMessage] = []
    @Published var isLoading = false
    @Published var streamingContent = ""
    @Published var isStreaming = false
    
    private let apiService = ChatAPIService.shared
    private let messageService = ChatMessageService.shared
    
    // MARK: - Sessions
    
    func loadSessions() async {
        isLoading = true
        defer { isLoading = false }
        
        do {
            let fetchedSessions = try await apiService.fetchSessions()
            // Sort by most recent first (updatedAt descending)
            sessions = fetchedSessions.sorted { $0.updatedAt > $1.updatedAt }
        } catch {
            print("Error loading sessions: \(error)")
            if let decodingError = error as? DecodingError {
                print("Decoding error details: \(decodingError)")
            }
            // Keep existing sessions if fetch fails
        }
    }
    
    func createSession(title: String, scopeType: ChatScopeType, scopeId: Int? = nil) async {
        isLoading = true
        defer { isLoading = false }
        
        do {
            let session = try await apiService.createSession(title: title, scopeType: scopeType, scopeId: scopeId)
            sessions.insert(session, at: 0)
            activeSession = session
            messages = []
        } catch {
            print("Error creating session: \(error)")
        }
    }
    
    /// Create a new session with default name and return it immediately
    func createSessionAndReturn(scopeType: ChatScopeType = .allLibrary, scopeId: Int? = nil) async -> ICChatSession? {
        // Generate default title based on current date/time
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        let defaultTitle = "Chat \(formatter.string(from: Date()))"
        
        do {
            let session = try await apiService.createSession(title: defaultTitle, scopeType: scopeType, scopeId: scopeId)
            // Reload sessions to get the updated list with proper sorting
            await loadSessions()
            activeSession = session
            messages = []
            return session
        } catch {
            print("Error creating session: \(error)")
            return nil
        }
    }
    
    func deleteSession(_ session: ICChatSession) async {
        do {
            try await apiService.deleteSession(id: session.id)
            sessions.removeAll { $0.id == session.id }
            if activeSession?.id == session.id {
                activeSession = nil
                messages = []
            }
        } catch {
            print("Error deleting session: \(error)")
        }
    }
    
    func updateSessionTitle(_ session: ICChatSession, newTitle: String) async {
        do {
            let updatedSession = try await apiService.updateSessionTitle(id: session.id, title: newTitle)
            
            // Update in the sessions array
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index] = updatedSession
            }
            
            // Update active session if it's the one being renamed
            if activeSession?.id == session.id {
                activeSession = updatedSession
            }
        } catch {
            print("Error updating session title: \(error)")
        }
    }
    
    func getOrCreateSession(scopeType: ChatScopeType, scopeId: Int?, title: String) async -> ICChatSession? {
        isLoading = true
        defer { isLoading = false }
        
        // First, check if we already have this session loaded
        if let existingSession = sessions.first(where: { $0.scopeType == scopeType && $0.scopeId == scopeId }) {
            return existingSession
        }
        
        // If not, fetch all sessions and check (or implement a filtered fetch on backend)
        await loadSessions()
        
        if let existingSession = sessions.first(where: { $0.scopeType == scopeType && $0.scopeId == scopeId }) {
            return existingSession
        }
        
        // Create new session
        do {
            let session = try await apiService.createSession(title: title, scopeType: scopeType, scopeId: scopeId)
            sessions.insert(session, at: 0)
            return session
        } catch {
            print("Error creating session: \(error)")
            return nil
        }
    }
    
    func fetchWelcomeMessage(for session: ICChatSession) async {
        do {
            let text = try await KnowledgeService.shared.fetchContextualMessage(scopeType: session.scopeType, scopeId: session.scopeId)
            // Add as local message
            let welcomeMsg = ICChatMessage(
                id: -Int.random(in: 1...100000), // Temporary ID
                sessionId: session.id,
                role: .assistant,
                content: text,
                createdAt: Date()
            )
            messages.append(welcomeMsg)
        } catch {
            print("Error fetching welcome message: \(error)")
        }
    }
    
    func switchActiveSession(_ session: ICChatSession) async {
        // Only reload if switching to a different session
        let shouldReload = activeSession?.id != session.id
        activeSession = session
        
        if shouldReload {
            await loadMessages(for: session.id)
        }
    }
    
    // MARK: - Messages
    
    func loadMessages(for sessionId: Int) async {
        isLoading = true
        defer { isLoading = false }
        
        do {
            messages = try await apiService.fetchMessages(sessionId: sessionId)
        } catch {
            print("Error loading messages: \(error)")
        }
    }
    
    func sendMessage(_ content: String) async {
        guard let session = activeSession else { return }
        
        // Optimistic update? Or wait for server?
        // Let's wait for server to confirm user message saved
        
        do {
            let userMessage = try await messageService.sendMessage(sessionId: session.id, content: content)
            messages.append(userMessage)
            
            // Start streaming response
            startStreamingResponse(sessionId: session.id, messageId: userMessage.id)
            
        } catch {
            print("Error sending message: \(error)")
        }
    }
    
    private func startStreamingResponse(sessionId: Int, messageId: Int) {
        Task { @MainActor in
            isStreaming = true
            streamingContent = ""
            
            // Add a temporary placeholder message for the streaming content
            let tempMessage = ICChatMessage(
                id: -1, // Temporary ID
                sessionId: sessionId,
                role: .assistant,
                content: "",
                createdAt: Date()
            )
            messages.append(tempMessage)
            
            print("🔵 Starting SSE stream for session \(sessionId), message \(messageId)")
        }
        
        messageService.streamResponse(
            sessionId: sessionId,
            messageId: messageId,
            onChunk: { [weak self] content in
                Task { @MainActor in
                    guard let self = self else { return }
                    print("🟢 Received chunk: \(content.prefix(50))...")
                    self.streamingContent += content
                    
                    // Update the temporary message with accumulated content
                    if let lastIndex = self.messages.lastIndex(where: { $0.id == -1 }) {
                        self.messages[lastIndex] = ICChatMessage(
                            id: -1,
                            sessionId: sessionId,
                            role: .assistant,
                            content: self.streamingContent,
                            createdAt: Date()
                        )
                    }
                }
            },
            onEnd: { [weak self] in
                Task { @MainActor in
                    guard let self = self else { return }
                    print("🟡 Stream ended, finalizing message")
                    self.isStreaming = false
                    await self.finalizeStreamingMessage(sessionId: sessionId)
                }
            },
            onError: { [weak self] error in
                Task { @MainActor in
                    guard let self = self else { return }
                    print("🔴 Streaming error: \(error)")
                    self.isStreaming = false
                    
                    // Remove temporary message on error
                    self.messages.removeAll { $0.id == -1 }
                }
            }
        )
    }
    
    private func finalizeStreamingMessage(sessionId: Int) async {
        // Remove temporary message
        messages.removeAll { $0.id == -1 }
        
        // Fetch latest messages to get the full assistant message with ID from server
        await loadMessages(for: sessionId)
        streamingContent = ""
    }
}

