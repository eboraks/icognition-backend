//
//  AuthenticationView.swift
//  iso-app
//
//  Created by Eliran Boraks on 10/12/25.
//

import SwiftUI
import FirebaseAuth
import GoogleSignInSwift
import AuthenticationServices

struct AuthenticationView: View {
    // Use the shared managers from ContentView instead of creating new ones
    @EnvironmentObject private var googleAuthManager: AuthenticationManager
    @EnvironmentObject private var appleAuthManager: AppleAuthManager
    @State private var isSigningIn = false
    @State private var errorMessage: String?
    @State private var showingTerms = false
    @State private var showingPrivacy = false
    
    // Use whichever auth manager has an authenticated user
    private var isAuthenticated: Bool {
        googleAuthManager.isAuthenticated || appleAuthManager.isAuthenticated
    }
    
    private var currentUser: User? {
        googleAuthManager.currentUser ?? appleAuthManager.currentUser
    }
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                if isAuthenticated, let user = currentUser {
                    // Authenticated view
                    VStack(spacing: 20) {
                        Text("Welcome!")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                        
                        // Profile photo
                        if let photoURL = user.photoURL {
                            AsyncImage(url: photoURL) { image in
                                image
                                    .resizable()
                                    .scaledToFill()
                            } placeholder: {
                                ProgressView()
                            }
                            .frame(width: 100, height: 100)
                            .clipShape(Circle())
                        }
                        
                        // User information
                        VStack(spacing: 8) {
                            if let displayName = user.displayName {
                                Text(displayName)
                                    .font(.title2)
                                    .fontWeight(.medium)
                            }
                            
                            if let email = user.email {
                                Text(email)
                                    .font(.body)
                                    .foregroundColor(.secondary)
                            }
                        }
                        
                        Spacer()
                        
                        // Sign out button
                        Button(action: {
                            googleAuthManager.signOut()
                            appleAuthManager.signOut()
                        }) {
                            Text("Sign Out")
                                .fontWeight(.semibold)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(Color.red)
                                .cornerRadius(10)
                        }
                        .padding(.horizontal)
                    }
                    .padding()
                    
                } else {
                    // Not authenticated view - Official Design
                    ZStack {
                        // Background layer - adapts to dark/light mode
                        Color(.systemBackground)
                            .ignoresSafeArea()
                        
                        VStack(spacing: 0) {
                            Spacer()
                            
                            // Logo and App Name Section
                        VStack(spacing: 16) {
                            // App Logo - Larger size to replace text (using transparent background)
                            Image("icog_logo")
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 260, height: 100)
                            
                            // Tagline
                            Text("Your personal Knowledge Base AI Assistant")
                                .font(.system(size: 16, weight: .regular))
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal, 40)
                        }
                        
                        Spacer()
                        
                        // Sign-In Buttons Section
                        VStack(spacing: 16) {
                            // Apple Sign-In Button (Official Style)
                            SignInWithAppleButton(.signIn) { request in
                                appleAuthManager.handleSignInWithAppleRequest(request)
                            } onCompletion: { result in
                                Task {
                                    await appleAuthManager.handleSignInWithAppleCompletion(result)
                                }
                            }
                            .signInWithAppleButtonStyle(.black)
                            .frame(maxWidth: .infinity)
                            .frame(height: 50)
                            .cornerRadius(8)
                            .disabled(isSigningIn)
                            
                            // Google Sign-In Button (Custom Style matching Apple button)
                            Button(action: {
                                isSigningIn = true
                                errorMessage = nil
                                Task {
                                    do {
                                        try await googleAuthManager.signInWithGoogle()
                                    } catch {
                                        errorMessage = error.localizedDescription
                                    }
                                    isSigningIn = false
                                }
                            }) {
                                HStack(spacing: 0) {
                                    // Official Google Icon
                                    Image("GoogleIcon")
                                        .resizable()
                                        .aspectRatio(contentMode: .fit)
                                        .frame(width: 20, height: 20)
                                    
                                    Text("Sign in with Google")
                                        .font(.system(size: 17, weight: .semibold))
                                        .foregroundColor(.white)
                                        .padding(.leading, 12)
                                }
                                .frame(maxWidth: .infinity)
                                .frame(height: 50)
                                .background(Color.black)
                                .cornerRadius(8)
                            }
                            .disabled(isSigningIn)
                            
                            // Loading indicator
                            if isSigningIn {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle())
                                    .padding(.top, 8)
                            }
                            
                            // Error message
                            if let errorMessage = appleAuthManager.errorMessage ?? errorMessage {
                                Text(errorMessage)
                                    .foregroundColor(.red)
                                    .font(.caption)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal)
                                    .padding(.top, 8)
                            }
                        }
                        .padding(.horizontal, 24)
                        
                        Spacer()
                        
                        // Legal Text Section
                        VStack(spacing: 8) {
                            Text("By signing in, you agree to our")
                                .font(.system(size: 14))
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                            
                            HStack(spacing: 4) {
                                Button("Terms of Service") {
                                    showingTerms = true
                                }
                                .font(.system(size: 14))
                                .foregroundColor(.blue)
                                
                                Text("and")
                                    .font(.system(size: 14))
                                    .foregroundColor(.secondary)
                                
                                Button("Privacy Policy") {
                                    showingPrivacy = true
                                }
                                .font(.system(size: 14))
                                .foregroundColor(.blue)
                            }
                        }
                        .padding(.horizontal, 40)
                        .padding(.bottom, 40)
                        }
                    }
                }
            }
            .navigationBarHidden(true)
        }
        .sheet(isPresented: $showingTerms) {
            NavigationView {
                TermsOfServiceView()
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Done") {
                                showingTerms = false
                            }
                        }
                    }
            }
        }
        .sheet(isPresented: $showingPrivacy) {
            NavigationView {
                PrivacyPolicyView()
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Done") {
                                showingPrivacy = false
                            }
                        }
                    }
            }
        }
    }
}

#Preview {
    AuthenticationView()
        .environmentObject(AuthenticationManager())
        .environmentObject(AppleAuthManager())
}

