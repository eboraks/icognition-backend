//
//  AuthenticationManager.swift
//  iso-app
//
//  Created by Eliran Boraks on 10/12/25.
//

import SwiftUI
import FirebaseAuth
import FirebaseCore
import GoogleSignIn
import os.log

@MainActor
class AuthenticationManager: ObservableObject {
    @Published var currentUser: User?
    @Published var isAuthenticated = false
    
    private var authStateHandler: AuthStateDidChangeListenerHandle?
    
    init() {
        // Set up Firebase auth state listener for persistence
        authStateHandler = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            self?.currentUser = user
            self?.isAuthenticated = user != nil
            
            // Save user ID to shared UserDefaults for ShareExtension access
            if let user = user {
                self?.saveUserToSharedDefaults(user)
                // Only save token if this manager is handling the current user
                if self?.currentUser?.uid == user.uid {
                    Task {
                        await self?.saveFirebaseTokenForSharedAccess(user)
                    }
                }
            } else {
                self?.clearUserFromSharedDefaults()
                // Also clear tokens
                if let previousUserID = self?.currentUser?.uid {
                    TokenManager.shared.deleteTokens(for: previousUserID)
                }
            }
        }
        
        // IMPORTANT: Also save immediately if user is already authenticated
        if let currentUser = Auth.auth().currentUser {
            AppLogger.auth("User already authenticated on init, saving to shared defaults...", level: .info)
            saveUserToSharedDefaults(currentUser)
            
            // Also save Firebase token for ShareExtension
            Task {
                await saveFirebaseTokenForSharedAccess(currentUser)
            }
        }
    }
    
    // MARK: - Shared UserDefaults for ShareExtension
    
    private func saveUserToSharedDefaults(_ user: User) {
        AppLogger.auth("Attempting to save user to shared UserDefaults...", level: .info)
        AppLogger.auth("User ID: \(user.uid)", level: .debug)
        AppLogger.auth("Email: \(user.email ?? "nil")", level: .debug)
        AppLogger.auth("Display Name: \(user.displayName ?? "nil")", level: .debug)
        
        guard let sharedDefaults = UserDefaults(suiteName: "group.com.icognition.app") else {
            AppLogger.auth("CRITICAL: Failed to access shared UserDefaults", level: .error)
            AppLogger.auth("This means App Groups is NOT configured for main app target!", level: .error)
            return
        }
        
        AppLogger.auth("Successfully accessed shared UserDefaults", level: .info)
        
        sharedDefaults.set(user.uid, forKey: "testUserID")
        sharedDefaults.set(user.uid, forKey: "currentUserID")
        sharedDefaults.set(user.email, forKey: "userEmail")
        sharedDefaults.set(user.displayName, forKey: "userDisplayName")
        
        let syncSuccess = sharedDefaults.synchronize()
        AppLogger.auth("UserDefaults synchronize result: \(syncSuccess)", level: .debug)
        
        // Verify the save by reading back
        let savedUserID = sharedDefaults.string(forKey: "testUserID")
        AppLogger.auth("Verification - testUserID saved as: \(savedUserID ?? "nil")", level: .debug)
        
        if savedUserID == user.uid {
            AppLogger.auth("SUCCESSFULLY saved user info to shared UserDefaults for ShareExtension", level: .info)
            AppLogger.auth("User ID: \(user.uid)", level: .debug)
            AppLogger.auth("Email: \(user.email ?? "nil")", level: .debug)
            AppLogger.auth("Display Name: \(user.displayName ?? "nil")", level: .debug)
        } else {
            AppLogger.auth("FAILED: Saved user ID doesn't match! Expected: \(user.uid), Got: \(savedUserID ?? "nil")", level: .error)
        }
        
        // Also check the container path
        if let containerURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.icognition.app") {
            AppLogger.auth("App Group container path: \(containerURL.path)", level: .debug)
        } else {
            AppLogger.auth("Cannot access App Group container - App Groups NOT configured!", level: .error)
        }
    }
    
    private func clearUserFromSharedDefaults() {
        guard let sharedDefaults = UserDefaults(suiteName: "group.com.icognition.app") else {
            return
        }
        
        sharedDefaults.removeObject(forKey: "testUserID")
        sharedDefaults.removeObject(forKey: "currentUserID")
        sharedDefaults.removeObject(forKey: "userEmail")
        sharedDefaults.removeObject(forKey: "userDisplayName")
        sharedDefaults.synchronize()
        
        AppLogger.auth("Cleared user info from shared UserDefaults", level: .info)
    }
    
    /// Save Firebase token to shared Keychain for ShareExtension access
    private func saveFirebaseTokenForSharedAccess(_ user: User) async {
        AppLogger.auth("Saving Firebase token for ShareExtension access...", level: .info)
        
        do {
            // Get fresh Firebase ID token
            let idToken = try await user.getIDToken()
            AppLogger.auth("Got Firebase ID token (\(idToken.prefix(20))...)", level: .debug)
            
            // Save to shared Keychain via TokenManager
            TokenManager.shared.saveFirebaseToken(idToken, for: user.uid)
            AppLogger.auth("Firebase token saved for ShareExtension access", level: .info)
            
        } catch {
            AppLogger.auth("Failed to save Firebase token: \(error)", level: .error)
        }
    }
    
    deinit {
        if let authStateHandler = authStateHandler {
            Auth.auth().removeStateDidChangeListener(authStateHandler)
        }
    }
    
    func signInWithGoogle() async throws {
        AppLogger.auth("Starting Google Sign-In...", level: .info)
        
        // Get the client ID from Firebase configuration
        guard let clientID = FirebaseApp.app()?.options.clientID else {
            AppLogger.auth("Missing client ID", level: .error)
            throw AuthError.missingClientID
        }
        
        AppLogger.auth("Client ID: \(clientID)", level: .debug)
        
        // Configure Google Sign-In
        let config = GIDConfiguration(clientID: clientID)
        GIDSignIn.sharedInstance.configuration = config
        
        AppLogger.auth("Google Sign-In configured", level: .info)
        
        // Get the root view controller
        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootViewController = windowScene.windows.first?.rootViewController else {
            AppLogger.auth("No root view controller", level: .error)
            throw AuthError.noRootViewController
        }
        
        AppLogger.auth("Got root view controller", level: .debug)
        
        // Start the Google Sign-In flow
        AppLogger.auth("Presenting Google Sign-In...", level: .info)
        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: rootViewController)
        let user = result.user
        
        AppLogger.auth("Google Sign-In succeeded", level: .info)
        
        guard let idToken = user.idToken?.tokenString else {
            AppLogger.auth("Missing ID token", level: .error)
            throw AuthError.missingIDToken
        }
        
        let accessToken = user.accessToken.tokenString
        
        AppLogger.auth("Got tokens, signing in to Firebase...", level: .info)
        
        // Create Firebase credential from Google tokens
        let credential = GoogleAuthProvider.credential(withIDToken: idToken, accessToken: accessToken)
        
        // Sign in to Firebase with the Google credential
        try await Auth.auth().signIn(with: credential)
        
        AppLogger.auth("Firebase sign-in complete", level: .info)
    }
    
    func signOut() {
        do {
            // Sign out from Firebase
            try Auth.auth().signOut()
            
            // Sign out from Google
            GIDSignIn.sharedInstance.signOut()
            
        } catch {
            AppLogger.auth("Error signing out: \(error.localizedDescription)", level: .error)
        }
    }
}

// Custom errors
enum AuthError: LocalizedError {
    case missingClientID
    case noRootViewController
    case missingIDToken
    
    var errorDescription: String? {
        switch self {
        case .missingClientID:
            return "Missing Firebase client ID"
        case .noRootViewController:
            return "No root view controller found"
        case .missingIDToken:
            return "Missing ID token from Google Sign-In"
        }
    }
}

