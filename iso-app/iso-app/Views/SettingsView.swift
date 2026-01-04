//
//  SettingsView.swift
//  iso-app
//
//  Settings view with backend environment switcher
//

import SwiftUI
import os.log

struct SettingsView: View {
    @StateObject private var environmentManager = BackendEnvironmentManager.shared
    @State private var selectedEnvironment: BackendEnvironment
    @State private var showSaveConfirmation = false
    @State private var isTestingConnection = false
    @State private var connectionTestResult: String?
    @State private var showConnectionTestAlert = false
    
    init() {
        // Initialize with current environment
        _selectedEnvironment = State(initialValue: BackendEnvironmentManager.shared.currentEnvironment)
    }
    
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Backend Environment")) {
                    Text("Choose which backend server to connect to. Changes take effect immediately.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.vertical, 4)
                    
                    ForEach(BackendEnvironment.allCases, id: \.self) { environment in
                        HStack {
                            Button(action: {
                                selectedEnvironment = environment
                                // Apply immediately when selection changes
                                if selectedEnvironment != environmentManager.currentEnvironment {
                                    saveEnvironment()
                                }
                            }) {
                                HStack {
                                    Image(systemName: selectedEnvironment == environment ? "checkmark.circle.fill" : "circle")
                                        .foregroundColor(selectedEnvironment == environment ? .blue : .gray)
                                    
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(environment.label)
                                            .font(.headline)
                                            .foregroundColor(.primary)
                                        
                                        Text(environment.baseURL)
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                    
                                    Spacer()
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(PlainButtonStyle())
                        }
                        .padding(.vertical, 8)
                    }
                }
                
                Section {
                    HStack {
                        Image(systemName: "info.circle.fill")
                            .foregroundColor(.blue)
                        Text("Current: \(environmentManager.currentEnvironment.label)")
                            .font(.subheadline)
                    }
                    .padding(.vertical, 4)
                    
                    Button(action: {
                        testConnection()
                    }) {
                        HStack {
                            if isTestingConnection {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "network")
                            }
                            Text(isTestingConnection ? "Testing Connection..." : "Test Connection")
                        }
                    }
                    .disabled(isTestingConnection)
                    
                    if let result = connectionTestResult {
                        Text(result)
                            .font(.caption)
                            .foregroundColor(result.contains("Success") ? .green : .red)
                            .padding(.top, 4)
                    }
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                // Sync selected environment with current when view appears
                selectedEnvironment = environmentManager.currentEnvironment
            }
            .alert("Environment Changed", isPresented: $showSaveConfirmation) {
                Button("OK", role: .cancel) { }
            } message: {
                Text("Backend environment has been changed to \(selectedEnvironment.label). All API requests will now use \(selectedEnvironment.baseURL)")
            }
            .alert("Connection Test", isPresented: $showConnectionTestAlert) {
                Button("OK", role: .cancel) { }
            } message: {
                if let result = connectionTestResult {
                    Text(result)
                } else {
                    Text("Connection test completed")
                }
            }
        }
    }
    
    private func saveEnvironment() {
        environmentManager.setEnvironment(selectedEnvironment)
        showSaveConfirmation = true
        connectionTestResult = nil // Clear previous test result
        AppLogger.ui("User changed backend environment to: \(selectedEnvironment.label)", level: .info)
    }
    
    private func testConnection() {
        isTestingConnection = true
        connectionTestResult = nil
        
        Task {
            let (success, error) = await NetworkConnectivityTest.shared.testCurrentBackend()
            
            await MainActor.run {
                isTestingConnection = false
                if success {
                    connectionTestResult = "✅ Successfully connected to \(environmentManager.currentEnvironment.baseURL)"
                } else {
                    connectionTestResult = "❌ Connection failed: \(error ?? "Unknown error")\n\nTroubleshooting:\n• Ensure iPhone and Mac are on the same Wi-Fi network\n• Verify backend is running with: uvicorn app.main:app --host 0.0.0.0 --port 8000\n• Check Mac's IP hasn't changed"
                }
                showConnectionTestAlert = true
            }
        }
    }
}

// MARK: - Preview

#Preview {
    SettingsView()
}
