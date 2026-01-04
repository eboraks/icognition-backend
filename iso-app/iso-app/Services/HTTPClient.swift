//
//  HTTPClient.swift
//  iso-app
//
//  HTTP client with automatic token injection for backend API calls
//

import Foundation
import FirebaseAuth
import os.log

/// HTTP client with automatic token injection
class HTTPClient {
    static let shared = HTTPClient()
    
    private let session: URLSession
    private let environmentManager = BackendEnvironmentManager.shared
    private let timeout: TimeInterval = 30.0
    
    /// Current base URL from environment manager
    var baseURL: String {
        return environmentManager.currentBaseURL
    }
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = timeout
        self.session = URLSession(configuration: config)
        
        AppLogger.network("HTTPClient initialized with base URL: \(self.baseURL)", level: .info)
        AppLogger.network("Current environment: \(environmentManager.currentEnvironment.label)", level: .info)
    }
    
    // MARK: - Public Methods
    
    /// Make an authenticated GET request
    /// - Parameters:
    ///   - endpoint: The API endpoint (e.g., "/documents/123")
    ///   - requiresAuth: Whether to include auth token (default: false)
    /// - Returns: HTTP response data and status code
    func get(endpoint: String, requiresAuth: Bool = false) async throws -> (data: Data, statusCode: Int) {
        return try await makeRequest(
            method: "GET",
            endpoint: endpoint,
            body: nil,
            requiresAuth: requiresAuth
        )
    }
    
    /// Make an authenticated POST request
    /// - Parameters:
    ///   - endpoint: The API endpoint
    ///   - body: Request body data
    ///   - requiresAuth: Whether to include auth token (default: false)
    /// - Returns: HTTP response data and status code
    func post(endpoint: String, body: Data?, requiresAuth: Bool = false) async throws -> (data: Data, statusCode: Int) {
        return try await makeRequest(
            method: "POST",
            endpoint: endpoint,
            body: body,
            requiresAuth: requiresAuth
        )
    }
    
    /// Make an authenticated PUT request
    /// - Parameters:
    ///   - endpoint: The API endpoint
    ///   - body: Request body data
    ///   - requiresAuth: Whether to include auth token (default: false)
    /// - Returns: HTTP response data and status code
    func put(endpoint: String, body: Data?, requiresAuth: Bool = false) async throws -> (data: Data, statusCode: Int) {
        return try await makeRequest(
            method: "PUT",
            endpoint: endpoint,
            body: body,
            requiresAuth: requiresAuth
        )
    }
    
    /// Make an authenticated DELETE request
    /// - Parameters:
    ///   - endpoint: The API endpoint
    ///   - requiresAuth: Whether to include auth token (default: false)
    /// - Returns: HTTP response data and status code
    func delete(endpoint: String, requiresAuth: Bool = false) async throws -> (data: Data, statusCode: Int) {
        return try await makeRequest(
            method: "DELETE",
            endpoint: endpoint,
            body: nil,
            requiresAuth: requiresAuth
        )
    }
    
    // MARK: - Private Methods
    
    /// Make an HTTP request with automatic token injection
    private func makeRequest(
        method: String,
        endpoint: String,
        body: Data?,
        requiresAuth: Bool
    ) async throws -> (data: Data, statusCode: Int) {
        
        let fullURL = "\(baseURL)\(endpoint)"
        AppLogger.network("Making \(method) request to: \(fullURL)", level: .debug)
        
        guard let url = URL(string: fullURL) else {
            AppLogger.network("Failed to create URL from: \(fullURL)", level: .error)
            throw HTTPClientError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        
        // Add content type for requests with body
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        
        // Add auth token if authentication is required
        if requiresAuth {
            do {
                let token = try await getValidFirebaseToken()
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                AppLogger.auth("Added Firebase auth token", level: .debug)
                AppLogger.auth("Token prefix: \(String(token.prefix(20)))...", level: .debug)
            } catch {
                AppLogger.auth("Failed to get Firebase token: \(error.localizedDescription)", level: .error)
                throw HTTPClientError.authenticationFailed(error)
            }
        } else {
            AppLogger.network("Request does not require authentication", level: .debug)
        }
        
        // Add common headers
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("iCognition-iOS/1.0", forHTTPHeaderField: "User-Agent")
        
        do {
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw HTTPClientError.invalidResponse
            }
            
            // Log request details
            AppLogger.network("\(method) \(endpoint) - Status: \(httpResponse.statusCode)", level: .info)
            
            // Check for 401 and retry with refreshed token
            if httpResponse.statusCode == 401 && requiresAuth {
                AppLogger.auth("Got 401, refreshing token and retrying...", level: .info)
                do {
                    let refreshedToken = try await getValidFirebaseToken(forceRefresh: true)
                    request.setValue("Bearer \(refreshedToken)", forHTTPHeaderField: "Authorization")
                    AppLogger.auth("Retrying request with refreshed token", level: .debug)
                    
                    // Retry the request
                    let (retryData, retryResponse) = try await session.data(for: request)
                    
                    guard let retryHttpResponse = retryResponse as? HTTPURLResponse else {
                        throw HTTPClientError.invalidResponse
                    }
                    
                    AppLogger.network("Retry \(method) \(endpoint) - Status: \(retryHttpResponse.statusCode)", level: .info)
                    return (retryData, retryHttpResponse.statusCode)
                    
                } catch {
                    AppLogger.auth("Token refresh failed: \(error.localizedDescription)", level: .error)
                    throw HTTPClientError.authenticationFailed(error)
                }
            }
            
            return (data, httpResponse.statusCode)
            
        } catch {
            let errorDescription = error.localizedDescription
            let nsError = error as NSError
            AppLogger.network("Request failed: \(errorDescription)", level: .error)
            AppLogger.network("Error domain: \(nsError.domain), code: \(nsError.code)", level: .error)
            if let underlyingError = nsError.userInfo[NSUnderlyingErrorKey] as? NSError {
                AppLogger.network("Underlying error: \(underlyingError.localizedDescription)", level: .error)
            }
            AppLogger.network("Failed URL: \(fullURL)", level: .error)
            throw HTTPClientError.networkError(error)
        }
    }
    
    // MARK: - Token Management
    
    /// Get a valid Firebase token, refreshing if necessary
    /// - Parameter forceRefresh: Whether to force token refresh
    /// - Returns: Valid Firebase ID token
    private func getValidFirebaseToken(forceRefresh: Bool = false) async throws -> String {
        // First try to get current user from Firebase Auth
        guard let user = Auth.auth().currentUser else {
            AppLogger.auth("No authenticated Firebase user found", level: .error)
            throw HTTPClientError.notAuthenticated
        }
        
        AppLogger.auth("Getting Firebase token for user: \(user.uid) (forceRefresh: \(forceRefresh))", level: .debug)
        
        do {
            let token = try await user.getIDToken(forcingRefresh: forceRefresh)
            AppLogger.auth("Successfully obtained Firebase token", level: .debug)
            return token
        } catch {
            AppLogger.auth("Failed to get Firebase token: \(error.localizedDescription)", level: .error)
            
            // If token fetch failed, try to refresh the user's auth state
            AppLogger.auth("Attempting to refresh user auth state...", level: .info)
            
            // Force a token refresh
            do {
                let refreshedToken = try await user.getIDToken(forcingRefresh: true)
                AppLogger.auth("Successfully refreshed Firebase token", level: .info)
                return refreshedToken
            } catch {
                AppLogger.auth("Token refresh failed: \(error.localizedDescription)", level: .error)
                throw HTTPClientError.authenticationFailed(error)
            }
        }
    }
}

// MARK: - HTTP Client Errors

enum HTTPClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case networkError(Error)
    case authenticationFailed(Error)
    case notAuthenticated
    case serverError(Int)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .authenticationFailed(let error):
            return "Authentication failed: \(error.localizedDescription)"
        case .notAuthenticated:
            return "User is not authenticated"
        case .serverError(let code):
            return "Server error: \(code)"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .invalidURL:
            return "Check the endpoint URL"
        case .invalidResponse:
            return "Try again later"
        case .networkError:
            return "Check your internet connection"
        case .authenticationFailed, .notAuthenticated:
            return "Please sign in again"
        case .serverError:
            return "Try again later or contact support"
        }
    }
}

