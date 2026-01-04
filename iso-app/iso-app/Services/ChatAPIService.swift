//
//  ChatAPIService.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import Foundation
import FirebaseAuth

class ChatAPIService {
    static let shared = ChatAPIService()
    private let client = HTTPClient.shared
    
    private init() {}
    
    // MARK: - Sessions
    
    func fetchSessions() async throws -> [ICChatSession] {
        let (data, _) = try await client.get(endpoint: "/api/v1/chat/sessions", requiresAuth: true)
        return try JSONDecoder().decode([ICChatSession].self, from: data)
    }
    
    func createSession(title: String, scopeType: ChatScopeType, scopeId: Int? = nil) async throws -> ICChatSession {
        let payload = ChatSessionCreate(title: title, scopeType: scopeType, scopeId: scopeId)
        let body = try JSONEncoder().encode(payload)
        
        let (data, _) = try await client.post(endpoint: "/api/v1/chat/sessions", body: body, requiresAuth: true)
        return try JSONDecoder().decode(ICChatSession.self, from: data)
    }
    
    func deleteSession(id: Int) async throws {
        _ = try await client.delete(endpoint: "/api/v1/chat/sessions/\(id)", requiresAuth: true)
    }
    
    func updateSessionTitle(id: Int, title: String) async throws -> ICChatSession {
        let payload = ChatSessionTitleUpdate(title: title)
        let body = try JSONEncoder().encode(payload)
        
        let (data, _) = try await client.put(endpoint: "/api/v1/chat/sessions/\(id)/title", body: body, requiresAuth: true)
        return try JSONDecoder().decode(ICChatSession.self, from: data)
    }
    
    // MARK: - Messages
    
    func fetchMessages(sessionId: Int) async throws -> [ICChatMessage] {
        let (data, _) = try await client.get(endpoint: "/api/v1/chat/sessions/\(sessionId)/messages", requiresAuth: true)
        return try JSONDecoder().decode([ICChatMessage].self, from: data)
    }
}

