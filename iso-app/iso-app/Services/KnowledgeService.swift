//
//  KnowledgeService.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import Foundation

class KnowledgeService {
    static let shared = KnowledgeService()
    private let client = HTTPClient.shared
    
    private init() {}
    
    func fetchContextualMessage(scopeType: ChatScopeType, scopeId: Int?) async throws -> String {
        // This endpoint might return a JSON with a message field
        // Adjust payload as per API spec
        let payload: [String: Any] = [
            "scope_type": scopeType.rawValue,
            "scope_id": scopeId as Any
        ]
        
        // We need to encode mixed types manually or use a struct
        let requestBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, _) = try await client.post(endpoint: "/api/v1/knowledge/contextual-message", body: requestBody, requiresAuth: true)
        
        // Assuming response is {"message": "Welcome..."}
        struct Response: Codable {
            let message: String
        }
        
        let response = try JSONDecoder().decode(Response.self, from: data)
        return response.message
    }
}

