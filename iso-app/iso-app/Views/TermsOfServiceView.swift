//
//  TermsOfServiceView.swift
//  iso-app
//
//  Terms of Service page
//

import SwiftUI

struct TermsOfServiceView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Terms of Service")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom)
                
                Text("Last updated: \(Date().formatted(date: .abbreviated, time: .omitted))")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Group {
                    Text("1. Acceptance of Terms")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("By using iCognition.ai, you agree to be bound by these Terms of Service and all applicable laws and regulations.")
                    
                    Text("2. Description of Service")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("iCognition.ai is a personal knowledge base AI assistant that helps you save, organize, and analyze web content using artificial intelligence.")
                    
                    Text("3. User Accounts")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("You are responsible for maintaining the confidentiality of your account and password. You agree to accept responsibility for all activities that occur under your account.")
                    
                    Text("4. Privacy")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("Your privacy is important to us. Please review our Privacy Policy, which also governs your use of the service.")
                    
                    Text("5. Prohibited Uses")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("You may not use our service for any unlawful purpose or to solicit others to perform unlawful acts.")
                    
                    Text("6. Intellectual Property")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("The service and its original content, features, and functionality are owned by iCognition.ai and are protected by international copyright, trademark, and other intellectual property laws.")
                    
                    Text("7. Termination")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We may terminate or suspend your account immediately, without prior notice, for conduct that we believe violates these Terms of Service.")
                    
                    Text("8. Contact Information")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("If you have any questions about these Terms of Service, please contact us at support@icognition.ai")
                }
            }
            .padding()
        }
        .navigationTitle("Terms of Service")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationView {
        TermsOfServiceView()
    }
}
