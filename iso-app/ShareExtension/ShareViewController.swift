//
//  ShareViewController.swift
//  ShareExtension
//
//  Main entry point for the Share Extension
//

import UIKit
import SwiftUI
import LinkPresentation
import UniformTypeIdentifiers

@objc(ShareViewController)
class ShareViewController: UIViewController {
    private var viewModel: ShareExtensionViewModel?
    
    override func viewDidLoad() {
        super.viewDidLoad()
        print("🎯 ShareViewController: viewDidLoad called")
        
        Task {
            print("🎯 ShareViewController: Starting setupViewModel...")
            await setupViewModel()
            print("🎯 ShareViewController: setupViewModel completed")
        }
    }
    
    deinit {
        // Cleanup if needed
    }
    
    @MainActor
    private func setupViewModel() async {
        print("🎯 ShareViewController: Creating ShareExtensionViewModel...")
        let viewModel = ShareExtensionViewModel()
        self.viewModel = viewModel
        
        print("🎯 ShareViewController: Initializing viewModel with extension context...")
        // Initialize the view model with extension context
        await viewModel.initialize(with: extensionContext)
        
        print("🎯 ShareViewController: Creating SwiftUI view...")
        // Create the SwiftUI view with the view model
        let shareView = iCognitionShareView(
            viewModel: viewModel,
            extensionContext: extensionContext,
            onSave: { [weak self] in
                print("🎯 ShareViewController: Save button tapped")
                self?.handleSaveCompletion()
            },
            onCancel: { [weak self] in
                print("🎯 ShareViewController: Cancel button tapped")
                self?.cancelRequest()
            },
            onOpenLibrary: { [weak self] in
                print("🎯 ShareViewController: Open Library button tapped")
                self?.openMainAppLibrary()
            }
        )
        
        let hostingController = UIHostingController(rootView: shareView)
        
        addChild(hostingController)
        view.addSubview(hostingController.view)
        hostingController.didMove(toParent: self)
        
        hostingController.view.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            hostingController.view.topAnchor.constraint(equalTo: view.topAnchor),
            hostingController.view.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            hostingController.view.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            hostingController.view.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
    }
    
    private func handleSaveCompletion() {
        // Check if save was successful
        if let viewModel = viewModel, viewModel.saveSuccess {
            print("✅ Save was successful, closing extension")
            
            // Complete with success - this will close the extension
            // The main app will detect the saved content via app group data when opened
            extensionContext?.completeRequest(returningItems: [], completionHandler: { _ in
                print("✅ Share extension completed and closed successfully")
            })
        } else {
            print("❌ Save was not successful, closing extension normally")
            // Complete normally (user may have cancelled or there was an error)
            completeRequest()
        }
    }
    
    private func completeRequest() {
        extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
    }
    
    private func cancelRequest() {
        let error = NSError(domain: "ShareExtension", code: 0, userInfo: [NSLocalizedDescriptionKey: "User cancelled"])
        extensionContext?.cancelRequest(withError: error)
    }
    
    private func dismiss(with message: String) {
        let error = NSError(domain: "ShareExtension", code: 0, userInfo: [NSLocalizedDescriptionKey: message])
        extensionContext?.cancelRequest(withError: error)
    }
    
    private func openMainAppLibrary() {
        print("🚀 ShareViewController: Attempting to open main app Library...")
        
        guard let url = URL(string: "icognition://open?page=library") else {
            print("❌ Invalid library URL")
            cancelRequest()
            return
        }
        
        print("🔗 ShareViewController: Opening URL: \(url.absoluteString)")
        print("🔍 ShareViewController: URL scheme: \(url.scheme ?? "nil")")
        print("🔍 ShareViewController: URL host: \(url.host ?? "nil")")
        print("🔍 ShareViewController: URL path: \(url.path)")
        
        // iOS 14.5+ method for opening URLs from extensions
        if #available(iOS 14.5, *) {
            extensionContext?.open(url, completionHandler: { [weak self] success in
                DispatchQueue.main.async {
                    if success {
                        print("✅ Main app Library opened successfully")
                    } else {
                        print("❌ Failed to open main app Library - URL scheme not registered or app not installed")
                        print("🔍 ShareViewController: This might mean:")
                        print("   - Main app is not installed")
                        print("   - URL scheme 'icognition' is not registered")
                        print("   - Main app is not running and can't be launched")
                        print("   - iOS security restrictions")
                        
                        // Try fallback: open app without specific path
                        print("🔄 ShareViewController: Trying fallback - opening main app...")
                        if let fallbackUrl = URL(string: "icognition://") {
                            self?.extensionContext?.open(fallbackUrl, completionHandler: { fallbackSuccess in
                                DispatchQueue.main.async {
                                    if fallbackSuccess {
                                        print("✅ Fallback successful - main app opened")
                                    } else {
                                        print("❌ Fallback also failed")
                                    }
                                    self?.cancelRequest()
                                }
                            })
                        } else {
                            self?.cancelRequest()
                        }
                        return
                    }
                    // Close the extension after attempting to open
                    self?.cancelRequest()
                }
            })
        } else {
            // For older iOS versions, just close the extension
            print("⚠️ iOS version too old for extensionContext.open(), closing extension")
            cancelRequest()
        }
    }
    
}
