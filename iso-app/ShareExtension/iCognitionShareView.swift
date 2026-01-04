//
//  iCognitionShareView.swift
//  ShareExtension
//
//  SwiftUI interface for the Share Extension
//

import SwiftUI
import UIKit

struct iCognitionShareView: View {
    @ObservedObject var viewModel: ShareExtensionViewModel
    let extensionContext: NSExtensionContext?
    let onSave: () -> Void
    let onCancel: () -> Void
    let onOpenLibrary: () -> Void  // New callback for opening library
    
    @State private var showingError = false
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Header
                HStack {
                    Button("Cancel") {
                        onCancel()
                    }
                    .foregroundColor(.blue)
                    
                    Spacer()
                    
                    Text("Save to iCognition")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Spacer()
                    
                    HStack(spacing: 12) {
                        Button("Open Library") {
                            onOpenLibrary()
                        }
                        .foregroundColor(.blue)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        
                        Button("Save") {
                            Task {
                                do {
                                    try await viewModel.saveContent(with: extensionContext)
                                    // Call onSave callback to trigger extension completion
                                    onSave()
                                } catch {
                                    viewModel.errorMessage = error.localizedDescription
                                    showingError = true
                                }
                            }
                        }
                        .foregroundColor(.blue)
                        .fontWeight(.semibold)
                        .disabled(!viewModel.canSave)
                    }
                }
                .padding()
                .background(Color(UIColor.systemBackground))
                
                Divider()
                
                // Content
                VStack(alignment: .leading, spacing: 16) {
                    // Title field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Title")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(.secondary)
                        
                        TextField("Enter title", text: $viewModel.title)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .font(.body)
                    }
                    
                    // URL display
                    VStack(alignment: .leading, spacing: 8) {
                        Text("URL")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(.secondary)
                        
                        HStack {
                            Image(systemName: "link")
                                .foregroundColor(.blue)
                                .font(.system(size: 14))
                            
                            Text(viewModel.urlString)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                                .multilineTextAlignment(.leading)
                            
                            Spacer()
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color(UIColor.systemGray6))
                        .cornerRadius(8)
                    }
                    
                    Spacer()
                    
                    // Success message
                    if viewModel.saveSuccess {
                        HStack {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                                .font(.system(size: 20))
                            Text(viewModel.saveSuccessMessage ?? "Article saved successfully!")
                                .font(.subheadline)
                                .foregroundColor(.green)
                                .fontWeight(.medium)
                            Spacer()
                        }
                        .padding()
                        .background(Color.green.opacity(0.1))
                        .cornerRadius(8)
                    }
                    
                    // Loading indicator
                    if viewModel.isLoading {
                        HStack {
                            Spacer()
                            VStack(spacing: 8) {
                                ProgressView()
                                    .scaleEffect(1.2)
                                Text("Saving...")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                        }
                        .padding()
                    }
                    
                    // Error message
                    if let errorMessage = viewModel.errorMessage {
                        HStack {
                            Image(systemName: "exclamationmark.triangle")
                                .foregroundColor(.red)
                            Text(errorMessage)
                                .font(.subheadline)
                                .foregroundColor(.red)
                            Spacer()
                        }
                        .padding()
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(8)
                    }
                }
                .padding()
                .background(Color(UIColor.systemBackground))
                
                Spacer()
            }
            .background(Color(UIColor.systemGroupedBackground))
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }
    
}

#Preview {
    let viewModel = ShareExtensionViewModel()
    iCognitionShareView(
        viewModel: viewModel,
        extensionContext: nil,
        onSave: { },
        onCancel: { },
        onOpenLibrary: { }
    )
}

