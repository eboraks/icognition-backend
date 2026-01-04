//
//  EntityTree.swift
//  iso-app
//
//  Data models for entity tree structure from backend API
//

import Foundation

// MARK: - Entity Tree Response

/// Response model for entity tree structure
struct EntityTreeResponse: Codable {
    let tree: [EntityTreeNode]
}

// MARK: - Entity Tree Node

/// Tree node structure for entity filtering
struct EntityTreeNode: Codable, Identifiable {
    let key: String
    let label: String
    let children: [EntityTreeNode]?
    let data: EntityTreeNodeData?
    
    var id: String { key }
    
    enum CodingKeys: String, CodingKey {
        case key
        case label
        case children
        case data
    }
}

// MARK: - Entity Tree Node Data

/// Data payload for entity tree leaf nodes
struct EntityTreeNodeData: Codable {
    let entityId: Int
    let documentIds: [Int]
    
    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id"
        case documentIds = "document_ids"
    }
}
