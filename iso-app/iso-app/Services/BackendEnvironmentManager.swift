//
//  BackendEnvironmentManager.swift
//  iso-app
//
//  Manages backend environment configuration with UserDefaults storage
//

import Foundation
import os.log

/// Backend environment options for API connectivity
/// 
/// URLs are hardcoded here and can be modified if needed:
/// - Development: Points to local development server
///   - Simulator: Uses localhost (http://localhost:8000)
///   - Device: Uses hardcoded local network IP (http://172.20.0.141:8000)
///     ⚠️ NOTE: The device IP is hardcoded and may need to be updated to match
///     your Mac's current local network IP address. To find your Mac's IP:
///     Run: `ifconfig | grep "inet " | grep -v 127.0.0.1`
/// - Staging: Points to staging server (https://stg.api.icognition.ai)
enum BackendEnvironment: String, CaseIterable {
    case development = "development"
    case staging = "staging"
    
    var label: String {
        switch self {
        case .development:
            return "Development"
        case .staging:
            return "Staging"
        }
    }
    
    /// Returns the base URL for the selected environment
    /// 
    /// URLs are defined here:
    /// - Development simulator: http://localhost:8000
    /// - Development device: http://172.20.0.141:8000 (hardcoded - may need updating)
    /// - Staging: https://stg.api.icognition.ai
    var baseURL: String {
        switch self {
        case .development:
            // Use localhost for simulator
            #if targetEnvironment(simulator)
                return "http://localhost:8000"
            #else
                // For physical device, uses hardcoded local network IP
                // ⚠️ IMPORTANT: This IP (172.20.0.141) is hardcoded and may not match
                // your Mac's current local network IP address. If the device cannot
                // connect to the development server, update this value to your Mac's
                // current IP address. Find it by running:
                // `ifconfig | grep "inet " | grep -v 127.0.0.1`
                return "http://172.20.0.141:8000"
            #endif
        case .staging:
            return "https://stg.api.icognition.ai"
        }
    }
}

/// Manages backend environment configuration with persistent storage
///
/// This singleton manages the current backend environment selection and provides
/// the base URL for API requests. The environment preference is persisted in
/// UserDefaults and automatically loaded on app launch.
///
/// **URL Sources:**
/// - URLs are hardcoded in the `BackendEnvironment` enum's `baseURL` property
/// - Development device URL uses a hardcoded IP (172.20.0.141) that may need
///   to be updated to match your Mac's current local network IP
/// - To modify URLs, edit the `BackendEnvironment.baseURL` computed property
class BackendEnvironmentManager: ObservableObject {
    static let shared = BackendEnvironmentManager()
    
    private let environmentKey = "backendEnvironment"
    
    @Published var currentEnvironment: BackendEnvironment {
        didSet {
            saveEnvironment()
            AppLogger.network("Backend environment changed to: \(currentEnvironment.label) (\(currentEnvironment.baseURL))", level: .info)
        }
    }
    
    var currentBaseURL: String {
        return currentEnvironment.baseURL
    }
    
    private init() {
        // Load saved environment or default to development for local testing
        if let savedValue = UserDefaults.standard.string(forKey: environmentKey),
           let environment = BackendEnvironment(rawValue: savedValue) {
            self.currentEnvironment = environment
            AppLogger.network("Loaded saved backend environment: \(environment.label) (\(environment.baseURL))", level: .info)
        } else {
            // Default to development for local testing convenience
            // Change this to .staging if you prefer staging as default
            self.currentEnvironment = .development
            AppLogger.network("Using default backend environment: development (\(currentEnvironment.baseURL))", level: .info)
        }
    }
    
    private func saveEnvironment() {
        UserDefaults.standard.set(currentEnvironment.rawValue, forKey: environmentKey)
        AppLogger.network("Saved backend environment: \(currentEnvironment.label)", level: .debug)
    }
    
    func setEnvironment(_ environment: BackendEnvironment) {
        currentEnvironment = environment
    }
}
