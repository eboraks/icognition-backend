//
//  PrivacyPolicyView.swift
//  iso-app
//
//  Privacy Policy page
//

import SwiftUI

struct PrivacyPolicyView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Privacy Policy")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom)
                
                Text("Last updated: \(Date().formatted(date: .abbreviated, time: .omitted))")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Group {
                    Text("1. Information We Collect")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We collect information you provide directly to us, such as when you create an account, save content, or contact us for support.")
                    
                    Text("2. How We Use Your Information")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We use the information we collect to provide, maintain, and improve our services, process transactions, and communicate with you.")
                    
                    Text("3. Information Sharing")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We do not sell, trade, or otherwise transfer your personal information to third parties without your consent, except as described in this policy.")
                    
                    Text("4. Data Security")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We implement appropriate security measures to protect your personal information against unauthorized access, alteration, disclosure, or destruction.")
                    
                    Text("5. Cookies and Tracking")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We may use cookies and similar tracking technologies to enhance your experience and analyze usage patterns.")
                    
                    Text("6. Third-Party Services")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("Our service integrates with third-party authentication providers (Google, Apple) and AI services. Please review their privacy policies.")
                    
                    Text("7. Data Retention")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We retain your information for as long as your account is active or as needed to provide you services.")
                    
                    Text("8. Your Rights")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("You have the right to access, update, or delete your personal information. You may also opt out of certain communications.")
                    
                    Text("9. Children's Privacy")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("Our service is not intended for children under 13. We do not knowingly collect personal information from children under 13.")
                    
                    Text("10. Changes to This Policy")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new policy on this page.")
                    
                    Text("11. Contact Us")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Text("If you have any questions about this Privacy Policy, please contact us at privacy@icognition.ai")
                }
            }
            .padding()
        }
        .navigationTitle("Privacy Policy")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationView {
        PrivacyPolicyView()
    }
}
