//
//  TokenManager.swift
//  iso-app
//
//  Shared token management for main app and ShareExtension
//

import Foundation
import Security
import FirebaseAuth
import os.log

/// Manages Firebase tokens in shared Keychain for both main app and ShareExtension
class TokenManager {
    static let shared = TokenManager()
    
    private let serviceIdentifier = "com.icognition.iso-app.firebase"
    
    // Use the bundle identifier with team prefix for keychain sharing
    private var accessGroup: String {
        // For keychain sharing, use the bundle identifier, not the app group identifier
        guard let teamIdentifier = getTeamIdentifierFromKeychain() else {
            AppLogger.auth("Could not get team identifier, using bundle ID without prefix", level: .warning)
            return "com.icognition.iso-app"
        }
        
        let fullAccessGroup = "\(teamIdentifier)com.icognition.iso-app"
        AppLogger.auth("Using keychain access group: \(fullAccessGroup)", level: .debug)
        return fullAccessGroup
    }
    
    private init() {}
    
    // MARK: - Token Storage
    
    /// Save Firebase token to shared Keychain
    /// - Parameters:
    ///   - token: The Firebase ID token
    ///   - userID: The user's Firebase UID
    func saveFirebaseToken(_ token: String, for userID: String) {
        AppLogger.auth("Saving Firebase token for user: \(userID)", level: .info)
        
        let tokenData = TokenData(
            idToken: token,
            refreshToken: "", // Firebase handles refresh internally
            timestamp: Date().timeIntervalSince1970,
            userID: userID
        )
        
        do {
            let data = try JSONEncoder().encode(tokenData)
            
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: serviceIdentifier,
                kSecAttrAccount as String: userID,
                kSecAttrAccessGroup as String: accessGroup,
                kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            ]
            
            // Delete existing item first
            let deleteQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: serviceIdentifier,
                kSecAttrAccount as String: userID,
                kSecAttrAccessGroup as String: accessGroup
            ]
            SecItemDelete(deleteQuery as CFDictionary)
            
            // Add new item
            let status = SecItemAdd(query as CFDictionary, nil)
            
            AppLogger.auth("SecItemAdd status: \(status)", level: .debug)
            AppLogger.auth("Access group used: \(accessGroup)", level: .debug)
            AppLogger.auth("Service identifier: \(serviceIdentifier)", level: .debug)
            
            if status == errSecSuccess {
                AppLogger.auth("Successfully saved Firebase token", level: .info)
                
                // Verify by reading back
                if let retrievedToken = getStoredToken(for: userID) {
                    AppLogger.auth("Verification successful - token readable", level: .info)
                    AppLogger.auth("Token prefix: \(retrievedToken.idToken.prefix(20))...", level: .debug)
                    AppLogger.auth("Timestamp: \(retrievedToken.timestamp)", level: .debug)
                } else {
                    AppLogger.auth("Could not verify saved token", level: .warning)
                }
            } else {
                AppLogger.auth("Failed to save token, status: \(status)", level: .error)
                throw TokenManagerError.saveFailed(status)
            }
            
        } catch {
            AppLogger.auth("Error saving token: \(error)", level: .error)
        }
    }
    
    /// Get valid Firebase token for API calls
    /// - Parameter userID: The user's Firebase UID
    /// - Returns: A valid Firebase ID token
    func getValidToken(for userID: String) async throws -> String {
        AppLogger.auth("Getting valid token for user: \(userID)", level: .info)
        
        guard let storedToken = getStoredToken(for: userID) else {
            AppLogger.auth("No stored token found", level: .warning)
            throw TokenManagerError.tokenNotFound
        }
        
        AppLogger.auth("Found stored token from \(Date(timeIntervalSince1970: storedToken.timestamp))", level: .info)
        
        // Check if token is expired (Firebase tokens expire after 1 hour)
        let tokenAge = Date().timeIntervalSince1970 - storedToken.timestamp
        let oneHour: TimeInterval = 3600
        
        if tokenAge > oneHour {
            AppLogger.auth("Token is \(Int(tokenAge/60)) minutes old - likely expired", level: .warning)
            
            // Try to parse JWT to check actual expiration
            if let expirationTime = parseTokenExpiration(storedToken.idToken) {
                let expDate = Date(timeIntervalSince1970: expirationTime)
                let isExpired = Date() > expDate
                
                AppLogger.auth("Token expires at \(expDate)", level: .debug)
                AppLogger.auth("Is expired: \(isExpired)", level: .debug)
                
                if isExpired {
                    AppLogger.auth("Token is expired", level: .warning)
                    throw TokenManagerError.tokenExpired
                }
            } else {
                // If we can't parse expiration, assume expired if > 1 hour
                AppLogger.auth("Could not parse token expiration, assuming expired", level: .warning)
                throw TokenManagerError.tokenExpired
            }
        }
        
        AppLogger.auth("Token is valid, returning", level: .info)
        return storedToken.idToken
    }
    
    /// Delete stored tokens for user
    /// - Parameter userID: The user's Firebase UID
    func deleteTokens(for userID: String) {
        AppLogger.auth("Deleting tokens for user: \(userID)", level: .info)
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceIdentifier,
            kSecAttrAccount as String: userID,
            kSecAttrAccessGroup as String: accessGroup
        ]
        
        let status = SecItemDelete(query as CFDictionary)
        
        if status == errSecSuccess {
            AppLogger.auth("Successfully deleted tokens", level: .info)
        } else if status == errSecItemNotFound {
            AppLogger.auth("No tokens to delete", level: .warning)
        } else {
            AppLogger.auth("Failed to delete tokens, status: \(status)", level: .error)
        }
    }
    
    // MARK: - Private Methods
    
    private func getStoredToken(for userID: String) -> TokenData? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceIdentifier,
            kSecAttrAccount as String: userID,
            kSecAttrAccessGroup as String: accessGroup,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        
        guard status == errSecSuccess,
              let data = result as? Data else {
            if status != errSecItemNotFound {
                AppLogger.auth("Keychain error: \(status)", level: .error)
            }
            return nil
        }
        
        do {
            return try JSONDecoder().decode(TokenData.self, from: data)
        } catch {
            AppLogger.auth("Failed to decode token data: \(error)", level: .error)
            return nil
        }
    }
    
    /// Parse JWT token to get expiration time
    /// - Parameter token: JWT token string
    /// - Returns: Expiration timestamp or nil
    private func parseTokenExpiration(_ token: String) -> TimeInterval? {
        let components = token.split(separator: ".")
        guard components.count == 3 else { return nil }
        
        // Decode the payload (second component)
        var payload = String(components[1])
        
        // Add padding if needed for base64 decoding
        let remainder = payload.count % 4
        if remainder > 0 {
            payload += String(repeating: "=", count: 4 - remainder)
        }
        
        guard let data = Data(base64Encoded: payload),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let exp = json["exp"] as? TimeInterval else {
            return nil
        }
        
        return exp
    }
    
    /// Get team identifier by querying a keychain item
    private func getTeamIdentifierFromKeychain() -> String? {
        // Create a temporary keychain item to get the team identifier
        let tempKey = "temp-team-id-query"
        let tempData = Data("temp".utf8)
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: tempKey,
            kSecValueData as String: tempData,
            kSecReturnAttributes as String: true
        ]
        
        // Add the item temporarily
        var result: AnyObject?
        let addStatus = SecItemAdd(query as CFDictionary, &result)
        
        defer {
            // Clean up the temporary item
            let deleteQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrAccount as String: tempKey
            ]
            SecItemDelete(deleteQuery as CFDictionary)
        }
        
        guard addStatus == errSecSuccess,
              let attributes = result as? [String: Any],
              let accessGroup = attributes[kSecAttrAccessGroup as String] as? String else {
            return nil
        }
        
        // Extract team identifier from access group
        // Access group format: "TEAM123456.com.company.app" -> we want "TEAM123456."
        if let prefixRange = accessGroup.range(of: ".") {
            let teamId = String(accessGroup[..<accessGroup.index(after: prefixRange.lowerBound)])
            AppLogger.auth("Extracted team identifier: \(teamId)", level: .debug)
            return teamId
        }
        
        return nil
    }
}

// MARK: - Token Data Structure

struct TokenData: Codable {
    let idToken: String
    let refreshToken: String  // Empty for Firebase iOS SDK
    let timestamp: TimeInterval
    let userID: String
}

// MARK: - Token Manager Errors

enum TokenManagerError: LocalizedError {
    case tokenNotFound
    case tokenExpired
    case saveFailed(OSStatus)
    case retrievalFailed(OSStatus)
    case invalidToken
    
    var errorDescription: String? {
        switch self {
        case .tokenNotFound:
            return "No authentication token found"
        case .tokenExpired:
            return "Authentication token has expired"
        case .saveFailed(let status):
            return "Failed to save token to Keychain: \(status)"
        case .retrievalFailed(let status):
            return "Failed to retrieve token from Keychain: \(status)"
        case .invalidToken:
            return "Invalid or corrupted token"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .tokenNotFound, .tokenExpired, .invalidToken:
            return "Please open the main iCognition app to refresh authentication"
        case .saveFailed, .retrievalFailed:
            return "Check Keychain access permissions and try again"
        }
    }
}
