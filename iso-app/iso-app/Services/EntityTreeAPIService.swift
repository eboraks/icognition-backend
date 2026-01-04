//
//  EntityTreeAPIService.swift
//  iso-app
//
//  Service for fetching entity tree from backend API for filtering
//

import Foundation
import os.log

/// Service for fetching entity tree from backend API
class EntityTreeAPIService {
    static let shared = EntityTreeAPIService()
    
    private let httpClient = HTTPClient.shared
    private let logger = Logger(subsystem: "com.icognition.iso-app", category: "EntityTreeAPIService")
    
    private init() {}
    
    /// Fetches entity tree from backend API
    /// - Returns: EntityTreeResponse or nil if failed
    func fetchEntityTree() async -> EntityTreeResponse? {
        logger.info("📥 EntityTreeAPIService: Fetching entity tree")
        
        do {
            let endpoint = "/documents/entities/tree"
            let (data, statusCode) = try await httpClient.get(endpoint: endpoint, requiresAuth: true)
            
            logger.info("📥 EntityTreeAPIService: Response status \(statusCode)")
            
            if statusCode == 200 {
                let treeResponse = try JSONDecoder().decode(EntityTreeResponse.self, from: data)
                logger.info("✅ EntityTreeAPIService: Fetched entity tree with \(treeResponse.tree.count) root nodes")
                return treeResponse
            } else {
                logger.error("❌ EntityTreeAPIService: API returned status \(statusCode)")
                if let responseString = String(data: data, encoding: .utf8) {
                    logger.error("📄 EntityTreeAPIService: Response body: \(responseString.prefix(500))")
                }
                return nil
            }
            
        } catch {
            logger.error("❌ EntityTreeAPIService: Fetch failed: \(error.localizedDescription)")
            return nil
        }
    }
}
