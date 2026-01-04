//
//  AppleAuthManager.swift
//  iso-app
//
//  Apple Sign-In integration with Firebase Authentication
//

import SwiftUI
import FirebaseAuth
import AuthenticationServices
import CryptoKit
import os.log

@MainActor
class AppleAuthManager: NSObject, ObservableObject {
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    @Published var errorMessage: String?
    
    private var authStateHandler: AuthStateDidChangeListenerHandle?
    private var currentNonce: String?
    
    override init() {
        super.init()
        
        // Set up Firebase auth state listener
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
    
    // MARK: - Apple Sign-In
    
    func handleSignInWithAppleRequest(_ request: ASAuthorizationAppleIDRequest) {
        AppLogger.auth("Setting up Apple Sign-In request...", level: .info)
        
        // Generate nonce for security
        let nonce = randomNonceString()
        currentNonce = nonce
        
        request.requestedScopes = [.fullName, .email]
        request.nonce = sha256(nonce)
        
        AppLogger.auth("Apple Sign-In request configured with nonce", level: .info)
    }
    
    func handleSignInWithAppleCompletion(_ result: Result<ASAuthorization, Error>) async {
        AppLogger.auth("Processing Apple Sign-In result...", level: .info)
        
        do {
            switch result {
            case .success(let authorization):
                guard let appleIDCredential = authorization.credential as? ASAuthorizationAppleIDCredential else {
                    AppLogger.auth("Invalid credential type", level: .error)
                    throw AppleAuthError.invalidCredential
                }
                
                guard let nonce = currentNonce else {
                    AppLogger.auth("Missing nonce", level: .error)
                    throw AppleAuthError.missingNonce
                }
                
                guard let appleIDToken = appleIDCredential.identityToken else {
                    AppLogger.auth("Unable to fetch identity token", level: .error)
                    throw AppleAuthError.missingToken
                }
                
                guard let idTokenString = String(data: appleIDToken, encoding: .utf8) else {
                    AppLogger.auth("Unable to serialize token string from data", level: .error)
                    throw AppleAuthError.invalidToken
                }
                
                AppLogger.auth("Got Apple ID token", level: .info)
                
                // Create Firebase credential
                let credential = OAuthProvider.credential(
                    providerID: AuthProviderID.apple,
                    idToken: idTokenString,
                    rawNonce: nonce,
                    accessToken: nil
                )
                
                AppLogger.auth("Signing in to Firebase with Apple credential...", level: .info)
                
                // Sign in to Firebase
                let authResult = try await Auth.auth().signIn(with: credential)
                
                AppLogger.auth("Firebase sign-in successful", level: .info)
                
                // Update profile if this is a new user and we have name info
                if let fullName = appleIDCredential.fullName,
                   let givenName = fullName.givenName,
                   let familyName = fullName.familyName {
                    
                    let displayName = "\(givenName) \(familyName)"
                    AppLogger.auth("Updating user profile with name: \(displayName)", level: .info)
                    
                    let changeRequest = authResult.user.createProfileChangeRequest()
                    changeRequest.displayName = displayName
                    try await changeRequest.commitChanges()
                    
                    AppLogger.auth("Profile updated", level: .info)
                }
                
                errorMessage = nil
                
            case .failure(let error):
                AppLogger.auth("Apple Sign-In failed: \(error.localizedDescription)", level: .error)
                
                // Don't show error if user cancelled
                if let authError = error as? ASAuthorizationError,
                   authError.code == .canceled {
                    AppLogger.auth("User cancelled sign-in", level: .info)
                    return
                }
                
                errorMessage = error.localizedDescription
            }
            
        } catch {
            AppLogger.auth("Error during Apple Sign-In: \(error.localizedDescription)", level: .error)
            errorMessage = error.localizedDescription
        }
    }
    
    func signOut() {
        do {
            try Auth.auth().signOut()
            AppLogger.auth("Signed out successfully", level: .info)
            errorMessage = nil
        } catch {
            AppLogger.auth("Error signing out: \(error.localizedDescription)", level: .error)
            errorMessage = error.localizedDescription
        }
    }
    
    // MARK: - Nonce Generation
    
    private func randomNonceString(length: Int = 32) -> String {
        precondition(length > 0)
        let charset: [Character] = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        var result = ""
        var remainingLength = length
        
        while remainingLength > 0 {
            let randoms: [UInt8] = (0 ..< 16).map { _ in
                var random: UInt8 = 0
                let errorCode = SecRandomCopyBytes(kSecRandomDefault, 1, &random)
                if errorCode != errSecSuccess {
                    fatalError("Unable to generate nonce. SecRandomCopyBytes failed with OSStatus \(errorCode)")
                }
                return random
            }
            
            randoms.forEach { random in
                if remainingLength == 0 {
                    return
                }
                
                if random < charset.count {
                    result.append(charset[Int(random)])
                    remainingLength -= 1
                }
            }
        }
        
        return result
    }
    
    private func sha256(_ input: String) -> String {
        let inputData = Data(input.utf8)
        let hashedData = SHA256.hash(data: inputData)
        let hashString = hashedData.compactMap {
            String(format: "%02x", $0)
        }.joined()
        
        return hashString
    }
}

// MARK: - Errors

enum AppleAuthError: LocalizedError {
    case invalidCredential
    case missingNonce
    case missingToken
    case invalidToken
    
    var errorDescription: String? {
        switch self {
        case .invalidCredential:
            return "Invalid Apple ID credential"
        case .missingNonce:
            return "Missing nonce for security validation"
        case .missingToken:
            return "Missing identity token from Apple"
        case .invalidToken:
            return "Unable to parse identity token"
        }
    }
}

