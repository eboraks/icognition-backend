//
//  iso_appApp.swift
//  iso-app
//
//  Created by Eliran Boraks on 10/12/25.
//

import SwiftUI
import FirebaseCore
import FirebaseAuth
import GoogleSignIn

class AppDelegate: NSObject, UIApplicationDelegate {
  func application(_ application: UIApplication,
                   didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil) -> Bool {
    FirebaseApp.configure()

    return true
  }
  
  func application(_ app: UIApplication,
                   open url: URL,
                   options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
    AppLogger.main("Received URL: \(url.absoluteString)", level: .info)
    AppLogger.main("URL scheme: \(url.scheme ?? "nil")", level: .debug)
    AppLogger.main("URL host: \(url.host ?? "nil")", level: .debug)
    AppLogger.main("URL path: \(url.path)", level: .debug)
    
    // Handle Google Sign-In URLs
    if GIDSignIn.sharedInstance.handle(url) {
      AppLogger.main("Handled Google Sign-In URL", level: .info)
      return true
    }
    
    // Handle custom icognition:// URLs
    if url.scheme == "icognition" {
      AppLogger.main("Received icognition URL: \(url.absoluteString)", level: .info)
      
      // Post notification to ContentView to handle navigation
      NotificationCenter.default.post(
        name: NSNotification.Name("OpenLibraryFromShareExtension"),
        object: nil,
        userInfo: ["url": url]
      )
      
      AppLogger.main("Posted OpenLibraryFromShareExtension notification", level: .info)
      return true
    }
    
    AppLogger.main("URL not handled", level: .warning)
    return false
  }
}



@main
struct iso_appApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    
    init() {
        // Run Core Data migration on app launch
        Task {
            do {
                try await CoreDataMigrationService.shared.migrateFromJSON()
            } catch {
                AppLogger.storage("Migration failed: \(error.localizedDescription)", level: .error)
            }
        }
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.managedObjectContext, CoreDataStack.shared.viewContext)
                .preferredColorScheme(.light)
        }
    }
}
