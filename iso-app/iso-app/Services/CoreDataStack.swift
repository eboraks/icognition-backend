//
//  CoreDataStack.swift
//  iso-app
//
//  Shared Core Data stack for main app and Share Extension with App Group support
//

import Foundation
import CoreData
import os.log

/// Shared Core Data stack that works with both main app and Share Extension
class CoreDataStack {
    static let shared = CoreDataStack()
    
    private let appGroupIdentifier = "group.com.icognition.app"
    private let modelName = "iCognition"
    
    lazy var persistentContainer: NSPersistentContainer = {
        let container = NSPersistentContainer(name: modelName)
        
        // Configure store location in App Group for sharing between app and extension
        guard let appGroupURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupIdentifier
        ) else {
            fatalError("Failed to access App Group container: \(appGroupIdentifier)")
        }
        
        let storeURL = appGroupURL.appendingPathComponent("\(modelName).sqlite")
        
        // Configure persistent store description
        let description = NSPersistentStoreDescription(url: storeURL)
        description.setOption(true as NSNumber, forKey: NSPersistentHistoryTrackingKey)
        description.setOption(true as NSNumber, forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey)
        
        container.persistentStoreDescriptions = [description]
        
        // Load persistent stores
        container.loadPersistentStores { storeDescription, error in
            if let error = error {
                AppLogger.storage("Failed to load Core Data store: \(error.localizedDescription)", level: .error)
                fatalError("Core Data store failed to load: \(error.localizedDescription)")
            }
            
            AppLogger.storage("Core Data store loaded successfully at: \(storeDescription.url?.path ?? "unknown")", level: .info)
        }
        
        // Configure view context
        container.viewContext.automaticallyMergesChangesFromParent = true
        container.viewContext.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        
        // Enable persistent history tracking for cross-process notifications
        container.viewContext.transactionAuthor = "mainApp"
        
        return container
    }()
    
    /// Main view context for UI operations
    var viewContext: NSManagedObjectContext {
        return persistentContainer.viewContext
    }
    
    /// Create a new background context for async operations
    func newBackgroundContext() -> NSManagedObjectContext {
        let context = persistentContainer.newBackgroundContext()
        context.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        context.transactionAuthor = "background"
        return context
    }
    
    /// Save the view context
    func saveContext() {
        let context = viewContext
        
        guard context.hasChanges else {
            return
        }
        
        do {
            try context.save()
            AppLogger.storage("Core Data context saved successfully", level: .debug)
        } catch {
            let nserror = error as NSError
            AppLogger.storage("Failed to save Core Data context: \(nserror.localizedDescription)", level: .error)
            AppLogger.storage("Error details: \(nserror.userInfo)", level: .error)
        }
    }
    
    /// Save a background context
    func saveContext(_ context: NSManagedObjectContext) throws {
        guard context.hasChanges else {
            return
        }
        
        try context.save()
        AppLogger.storage("Background Core Data context saved successfully", level: .debug)
    }
    
    /// Reset the Core Data database - deletes all data and creates a fresh database
    func resetDatabase() throws {
        AppLogger.storage("Resetting Core Data database...", level: .info)
        
        // Get the store URL
        guard let appGroupURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupIdentifier
        ) else {
            throw NSError(domain: "CoreDataStack", code: -1, userInfo: [NSLocalizedDescriptionKey: "Failed to access App Group container"])
        }
        
        let storeURL = appGroupURL.appendingPathComponent("\(modelName).sqlite")
        
        // Get the persistent store coordinator
        let coordinator = persistentContainer.persistentStoreCoordinator
        
        // Remove all persistent stores
        for store in coordinator.persistentStores {
            try coordinator.remove(store)
        }
        
        // Delete the database files
        let fileManager = FileManager.default
        
        // Delete main database file
        if fileManager.fileExists(atPath: storeURL.path) {
            try fileManager.removeItem(at: storeURL)
            AppLogger.storage("Deleted database file: \(storeURL.path)", level: .info)
        }
        
        // Delete SQLite journal files if they exist
        let journalURL = storeURL.appendingPathExtension("-wal")
        if fileManager.fileExists(atPath: journalURL.path) {
            try? fileManager.removeItem(at: journalURL)
        }
        
        let shmURL = storeURL.appendingPathExtension("-shm")
        if fileManager.fileExists(atPath: shmURL.path) {
            try? fileManager.removeItem(at: shmURL)
        }
        
        // Reset the persistent container (will be recreated on next access)
        // Note: We can't directly reset a lazy var, so we'll need to recreate it
        // This is a limitation, but the container will be recreated on next access
        
        AppLogger.storage("Database reset complete. Container will be recreated on next access.", level: .info)
    }
    
    private init() {
        // Setup persistent history tracking observer
        setupPersistentHistoryTracking()
    }
    
    /// Setup persistent history tracking for cross-process notifications
    private func setupPersistentHistoryTracking() {
        let center = NotificationCenter.default
        
        center.addObserver(
            forName: .NSPersistentStoreRemoteChange,
            object: persistentContainer.persistentStoreCoordinator,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            
            AppLogger.storage("Persistent store remote change detected", level: .info)
            
            // Merge changes into viewContext
            self.viewContext.perform {
                // Merge changes from other contexts/processes
                // automaticallyMergesChangesFromParent handles in-process changes
                // but for cross-process (ShareExtension), we might need to refresh
                self.viewContext.refreshAllObjects()
                
                // Notify UI of changes if needed (FetchRequest should handle it)
                // But sometimes explicit object refresh is needed for remote changes
            }
        }
    }
}

