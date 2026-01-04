//
//  Logger.swift
//  iso-app
//
//  Centralized logging configuration using OSLog framework
//

import Foundation
import os.log

/// Centralized logging configuration for the iCognition iOS app
struct AppLogger {
    
    // MARK: - Subsystems
    
    /// Main app subsystem
    static let mainApp = Logger(subsystem: "com.icognition.iso-app", category: "main")
    
    /// Authentication subsystem
    static let auth = Logger(subsystem: "com.icognition.iso-app", category: "authentication")
    
    /// Content management subsystem
    static let content = Logger(subsystem: "com.icognition.iso-app", category: "content")
    
    /// Network/API subsystem
    static let network = Logger(subsystem: "com.icognition.iso-app", category: "network")
    
    /// Share Extension subsystem
    static let shareExtension = Logger(subsystem: "com.icognition.iso-app", category: "shareExtension")
    
    /// Data storage subsystem
    static let storage = Logger(subsystem: "com.icognition.iso-app", category: "storage")
    
    /// UI subsystem
    static let ui = Logger(subsystem: "com.icognition.iso-app", category: "ui")
    
    /// AI/Cache subsystem
    static let ai = Logger(subsystem: "com.icognition.iso-app", category: "ai")
    
    // MARK: - Convenience Methods with Enhanced Metadata
    
    /// Log authentication events with timestamp, filename, and line number
    static func auth(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        auth.log(level: level, "\(logMessage)")
    }
    
    /// Log content processing events with timestamp, filename, and line number
    static func content(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        content.log(level: level, "\(logMessage)")
    }
    
    /// Log network/API events with timestamp, filename, and line number
    static func network(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        network.log(level: level, "\(logMessage)")
    }
    
    /// Log Share Extension events with timestamp, filename, and line number
    static func shareExtension(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        shareExtension.log(level: level, "\(logMessage)")
    }
    
    /// Log storage events with timestamp, filename, and line number
    static func storage(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        storage.log(level: level, "\(logMessage)")
    }
    
    /// Log UI events with timestamp, filename, and line number
    static func ui(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        ui.log(level: level, "\(logMessage)")
    }
    
    /// Log AI/cache events with timestamp, filename, and line number
    static func ai(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        ai.log(level: level, "\(logMessage)")
    }
    
    /// Log main app events with timestamp, filename, and line number
    static func main(_ message: String, level: OSLogType = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = URL(fileURLWithPath: file).lastPathComponent
        let timestamp = DateFormatter.logTimestamp.string(from: Date())
        let logMessage = "[\(timestamp)] [\(fileName):\(line)] [\(function)] \(message)"
        mainApp.log(level: level, "\(logMessage)")
    }
}

// MARK: - Log Level Extensions

extension OSLogType {
    /// Debug level logging (only in debug builds)
    static let debug = OSLogType.debug
    
    /// Info level logging (default)
    static let info = OSLogType.info
    
    /// Notice level logging (important events)
    static let notice = OSLogType.default
    
    /// Error level logging (errors that don't crash the app)
    static let error = OSLogType.error
    
    /// Fault level logging (critical errors)
    static let fault = OSLogType.fault
    
    /// Warning level logging (using notice level)
    static let warning = OSLogType.default
}

// MARK: - DateFormatter Extension

extension DateFormatter {
    static let logTimestamp: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
        formatter.timeZone = TimeZone.current
        return formatter
    }()
}

// MARK: - Convenience Extensions

extension Logger {
    /// Log with debug level (only in debug builds)
    func debug(_ message: String) {
        log(level: .debug, "\(message)")
    }
    
    /// Log with info level
    func info(_ message: String) {
        log(level: .info, "\(message)")
    }
    
    /// Log with notice level
    func notice(_ message: String) {
        log(level: .notice, "\(message)")
    }
    
    /// Log with error level
    func error(_ message: String) {
        log(level: .error, "\(message)")
    }
    
    /// Log with fault level
    func fault(_ message: String) {
        log(level: .fault, "\(message)")
    }
}
