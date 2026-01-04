//
//  ChatModels.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import Foundation

// MARK: - Enums

enum ChatRole: String, Codable {
    case user
    case assistant
    case system
}

enum ChatScopeType: String, Codable {
    case allLibrary = "all_library"
    case collection
    case document
    case entity
    case unknown
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        // Handle null or missing values
        if container.decodeNil() {
            print("Warning: ChatScopeType is null, defaulting to allLibrary")
            self = .allLibrary
            return
        }
        
        let rawValue = try container.decode(String.self)
        
        // Handle known values
        switch rawValue.lowercased() {
        case "all_library", "alllibrary":
            self = .allLibrary
        case "collection":
            self = .collection
        case "document":
            self = .document
        case "entity":
            self = .entity
        default:
            // Log unknown values for debugging and default to allLibrary
            print("Warning: Unknown ChatScopeType value: '\(rawValue)', defaulting to allLibrary")
            self = .allLibrary
        }
    }
}

// MARK: - Data Models

struct ICChatSession: Codable, Identifiable, Hashable {
    let id: Int
    let title: String
    let scopeType: ChatScopeType
    let scopeId: Int?
    let createdAt: Date
    let updatedAt: Date
    
    // Hashable conformance - use id for hashing
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
    
    static func == (lhs: ICChatSession, rhs: ICChatSession) -> Bool {
        lhs.id == rhs.id
    }
    
    enum CodingKeys: String, CodingKey {
        case id
        case title
        case scopeType = "scope_type"
        case scopeId = "scope_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        id = try container.decode(Int.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        scopeType = try container.decode(ChatScopeType.self, forKey: .scopeType)
        scopeId = try container.decodeIfPresent(Int.self, forKey: .scopeId)
        
        // Decode ISO8601 date strings
        let createdAtString = try container.decode(String.self, forKey: .createdAt)
        let updatedAtString = try container.decode(String.self, forKey: .updatedAt)
        
        // Helper function to parse ISO8601 date
        func parseDate(_ dateString: String) throws -> Date {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            
            if let date = formatter.date(from: dateString) {
                return date
            }
            
            // Fallback to format without fractional seconds
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }
            
            throw DecodingError.dataCorruptedError(
                forKey: .createdAt,
                in: container,
                debugDescription: "Invalid date format: \(dateString)"
            )
        }
        
        createdAt = try parseDate(createdAtString)
        updatedAt = try parseDate(updatedAtString)
    }
}

struct ICChatMessage: Codable, Identifiable, Equatable {
    let id: Int
    let sessionId: Int
    let role: ChatRole
    let content: String
    let createdAt: Date
    
    // Equatable conformance - compare by id
    static func == (lhs: ICChatMessage, rhs: ICChatMessage) -> Bool {
        lhs.id == rhs.id
    }
    
    enum CodingKeys: String, CodingKey {
        case id
        case sessionId = "session_id"
        case role
        case content
        case createdAt = "created_at"
    }
    
    init(id: Int, sessionId: Int, role: ChatRole, content: String, createdAt: Date) {
        self.id = id
        self.sessionId = sessionId
        self.role = role
        self.content = content
        self.createdAt = createdAt
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        id = try container.decode(Int.self, forKey: .id)
        sessionId = try container.decode(Int.self, forKey: .sessionId)
        role = try container.decode(ChatRole.self, forKey: .role)
        content = try container.decode(String.self, forKey: .content)
        
        // Decode ISO8601 date string
        let createdAtString = try container.decode(String.self, forKey: .createdAt)
        
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        
        if let date = formatter.date(from: createdAtString) {
            createdAt = date
        } else {
            // Fallback to format without fractional seconds
            formatter.formatOptions = [.withInternetDateTime]
            if let fallbackDate = formatter.date(from: createdAtString) {
                createdAt = fallbackDate
            } else {
                throw DecodingError.dataCorruptedError(
                    forKey: .createdAt,
                    in: container,
                    debugDescription: "Invalid date format: \(createdAtString)"
                )
            }
        }
    }
}

// MARK: - API Request Models

struct ChatSessionCreate: Codable {
    let title: String
    let scopeType: ChatScopeType
    let scopeId: Int?
    
    enum CodingKeys: String, CodingKey {
        case title
        case scopeType = "scope_type"
        case scopeId = "scope_id"
    }
}

struct ChatSessionScopeUpdate: Codable {
    let scopeType: ChatScopeType
    let scopeId: Int?
    
    enum CodingKeys: String, CodingKey {
        case scopeType = "scope_type"
        case scopeId = "scope_id"
    }
}

struct ChatSessionTitleUpdate: Codable {
    let title: String
}

struct ChatMessageCreate: Codable {
    let content: String
}

