//
//  SessionChatView.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import SwiftUI
import ExyteChat

struct SessionChatView: View {
    let session: ICChatSession
    @ObservedObject var store: ChatStore
    @Environment(\.presentationMode) var presentationMode
    
    @State private var displayMessages: [Message] = []
    
    var body: some View {
        VStack(spacing: 0) {
            if store.isLoading && displayMessages.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ChatView(messages: displayMessages) { draft in
                    Task {
                        await store.sendMessage(draft.text)
                    }
                }
                .messageUseMarkdown(true)
                .id(session.id) // Ensure ChatView is unique per session
            }
        }
        .navigationTitle(session.title)
        .task {
            // Only switch and load if this isn't already the active session
            if store.activeSession?.id != session.id {
                await store.switchActiveSession(session)
            } else {
                // If already active but messages are empty, reload
                if store.messages.isEmpty {
                    await store.loadMessages(for: session.id)
                }
            }
            
            // Fetch welcome message only after loading messages and if still empty
            if store.messages.isEmpty {
                await store.fetchWelcomeMessage(for: session)
            }
        }
        .onChange(of: store.messages) { newMessages in
            // Update display messages when store messages change (outside of view update)
            DispatchQueue.main.async {
                displayMessages = mapMessages(newMessages)
            }
        }
        .onAppear {
            // Initialize display messages
            DispatchQueue.main.async {
                displayMessages = mapMessages(store.messages)
            }
        }
    }
    
    private func mapMessages(_ chatMessages: [ICChatMessage]) -> [Message] {
        return chatMessages.map { chatMsg in
            let user = User(
                id: chatMsg.role == .user ? "user" : "assistant",
                name: chatMsg.role == .user ? "Me" : "AI",
                avatarURL: nil,
                isCurrentUser: chatMsg.role == .user
            )
            
            // Convert HTML to plain text or markdown-compatible format
            let displayText = convertHTMLToDisplayText(chatMsg.content)
            
            return Message(
                id: String(chatMsg.id),
                user: user,
                status: .sent,
                createdAt: chatMsg.createdAt,
                text: displayText
            )
        }
    }
    
    private func convertHTMLToDisplayText(_ html: String) -> String {
        // Try to parse HTML to AttributedString, then extract plain text
        if let data = html.data(using: .utf8) {
            do {
                let attributedString = try NSAttributedString(
                    data: data,
                    options: [
                        .documentType: NSAttributedString.DocumentType.html,
                        .characterEncoding: String.Encoding.utf8.rawValue
                    ],
                    documentAttributes: nil
                )
                return attributedString.string
            } catch {
                // If HTML parsing fails, strip tags manually
                return stripHTMLTags(html)
            }
        }
        return html
    }
    
    private func stripHTMLTags(_ html: String) -> String {
        var text = html
        
        // Replace common HTML entities
        text = text.replacingOccurrences(of: "&amp;", with: "&")
        text = text.replacingOccurrences(of: "&lt;", with: "<")
        text = text.replacingOccurrences(of: "&gt;", with: ">")
        text = text.replacingOccurrences(of: "&quot;", with: "\"")
        text = text.replacingOccurrences(of: "&#39;", with: "'")
        text = text.replacingOccurrences(of: "&nbsp;", with: " ")
        
        // Convert <br> to newlines
        text = text.replacingOccurrences(of: "<br>", with: "\n", options: .caseInsensitive)
        text = text.replacingOccurrences(of: "<br/>", with: "\n", options: .caseInsensitive)
        text = text.replacingOccurrences(of: "<br />", with: "\n", options: .caseInsensitive)
        
        // Convert </p> to double newlines
        text = text.replacingOccurrences(of: "</p>", with: "\n\n", options: .caseInsensitive)
        
        // Convert list items to bullet points
        text = text.replacingOccurrences(of: "<li>", with: "\n• ", options: .caseInsensitive)
        text = text.replacingOccurrences(of: "</li>", with: "", options: .caseInsensitive)
        
        // Remove all remaining HTML tags
        text = text.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
        
        // Clean up multiple newlines
        text = text.replacingOccurrences(of: "\n\n\n+", with: "\n\n", options: .regularExpression)
        
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
