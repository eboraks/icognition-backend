//
//  AppHeaderView.swift
//  iso-app
//
//  Created by AI Assistant on 12/6/25.
//

import SwiftUI
import FirebaseAuth
import GoogleSignIn

struct AppHeaderView: View {
    @State private var showingLogoutAlert = false
    
    // Get current user from Firebase Auth
    private var currentUser: User? {
        Auth.auth().currentUser
    }
    
    // Get user initials
    private var userInitials: String {
        guard let user = currentUser else { return "?" }
        
        if let displayName = user.displayName, !displayName.isEmpty {
            let components = displayName.components(separatedBy: " ")
            if components.count >= 2 {
                let first = String(components[0].prefix(1)).uppercased()
                let last = String(components[components.count - 1].prefix(1)).uppercased()
                return "\(first)\(last)"
            } else if let first = components.first {
                return String(first.prefix(1)).uppercased()
            }
        } else if let email = user.email, !email.isEmpty {
            return String(email.prefix(1)).uppercased()
        }
        
        return "?"
    }
    
    var body: some View {
        HStack {
            // Logo (left, with some spacing from edge) - larger size
            Image("icog_logo")
                .resizable()
                .scaledToFit()
                .frame(width: 188, height: 80)
            
            Spacer()
            
            // User menu (right)
            Menu {
                if let user = currentUser {
                    if let displayName = user.displayName {
                        Text(displayName)
                            .font(.headline)
                    }
                    if let email = user.email {
                        Text(email)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    
                    Divider()
                    
                    Button(role: .destructive, action: {
                        showingLogoutAlert = true
                    }) {
                        Label("Sign Out", systemImage: "arrow.right.square")
                    }
                }
            } label: {
                // User avatar with initials
                ZStack {
                    Circle()
                        .fill(Color.blue)
                        .frame(width: 36, height: 36)
                    
                    Text(userInitials)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .alert("Sign Out", isPresented: $showingLogoutAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Sign Out", role: .destructive) {
                signOut()
            }
        } message: {
            Text("Are you sure you want to sign out?")
        }
    }
    
    private func signOut() {
        do {
            // Sign out from Firebase
            try Auth.auth().signOut()
            
            // Sign out from Google
            GIDSignIn.sharedInstance.signOut()
            
            // The AuthenticationManager and AppleAuthManager will automatically
            // detect the sign out via their auth state listeners
        } catch {
            print("Error signing out: \(error.localizedDescription)")
        }
    }
}

