//
//  NetworkConnectivityTest.swift
//  iso-app
//
//  Utility to test network connectivity to backend
//

import Foundation
import os.log

class NetworkConnectivityTest {
    static let shared = NetworkConnectivityTest()
    
    /// Test connectivity to a given URL
    func testConnection(to urlString: String, timeout: TimeInterval = 5.0) async -> (success: Bool, error: String?) {
        guard let url = URL(string: urlString) else {
            return (false, "Invalid URL: \(urlString)")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = timeout
        request.setValue("iCognition-iOS/1.0", forHTTPHeaderField: "User-Agent")
        
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            
            if let httpResponse = response as? HTTPURLResponse {
                AppLogger.network("Connectivity test to \(urlString): Status \(httpResponse.statusCode)", level: .info)
                return (true, nil)
            } else {
                return (false, "Invalid response type")
            }
        } catch {
            let nsError = error as NSError
            let errorMsg = "Connection failed: \(error.localizedDescription) (domain: \(nsError.domain), code: \(nsError.code))"
            AppLogger.network("Connectivity test to \(urlString) failed: \(errorMsg)", level: .error)
            return (false, errorMsg)
        }
    }
    
    /// Test connectivity to the current backend environment
    func testCurrentBackend() async -> (success: Bool, error: String?) {
        let baseURL = BackendEnvironmentManager.shared.currentBaseURL
        let testURL = "\(baseURL)/health"
        AppLogger.network("Testing connectivity to current backend: \(testURL)", level: .info)
        return await testConnection(to: testURL)
    }
}
