//
//  ChatMessageService.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import Foundation

class ChatMessageService {
    static let shared = ChatMessageService()
    private let client = HTTPClient.shared
    private let sseClient = SSEClient.shared
    
    private init() {}
    
    func sendMessage(sessionId: Int, content: String) async throws -> ICChatMessage {
        let payload = ChatMessageCreate(content: content)
        let body = try JSONEncoder().encode(payload)
        
        let (data, _) = try await client.post(endpoint: "/api/v1/chat/sessions/\(sessionId)/messages", body: body, requiresAuth: true)
        return try JSONDecoder().decode(ICChatMessage.self, from: data)
    }
    
    func streamResponse(
        sessionId: Int,
        messageId: Int,
        onChunk: @escaping (String) -> Void,
        onEnd: @escaping () -> Void,
        onError: @escaping (Error) -> Void
    ) {
        sseClient.streamChatResponse(
            sessionId: sessionId,
            messageId: messageId,
            onChunk: onChunk,
            onEnd: onEnd,
            onError: onError
        )
    }
}

