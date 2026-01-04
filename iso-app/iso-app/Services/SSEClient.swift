//
//  SSEClient.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import Foundation
import FirebaseAuth

enum SSEError: Error {
    case connectionFailed
    case invalidResponse
    case streamTerminated
    case notAuthenticated
}

class SSEClient: NSObject {
    static let shared = SSEClient()
    
    private var session: URLSession!
    private var activeTask: URLSessionDataTask?
    private var onChunk: ((String) -> Void)?
    private var onEnd: (() -> Void)?
    private var onError: ((Error) -> Void)?
    
    override init() {
        super.init()
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = TimeInterval.infinity // Keep connection open
        config.timeoutIntervalForResource = TimeInterval.infinity
        self.session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }
    
    func streamChatResponse(
        sessionId: Int,
        messageId: Int,
        onChunk: @escaping (String) -> Void,
        onEnd: @escaping () -> Void,
        onError: @escaping (Error) -> Void
    ) {
        // Cancel any existing task
        cancelStream()
        
        self.onChunk = onChunk
        self.onEnd = onEnd
        self.onError = onError
        
        let baseURL = HTTPClient.shared.baseURL
        // ✅ CORRECT - Using query parameter, not path parameter
        let endpoint = "/api/v1/chat/sessions/\(sessionId)/stream?message_id=\(messageId)"
        guard let url = URL(string: "\(baseURL)\(endpoint)") else {
            onError(SSEError.invalidResponse)
            return
        }
        
        // Fetch token and start request
        Task {
            do {
                guard let user = Auth.auth().currentUser else {
                    throw SSEError.notAuthenticated
                }
                let token = try await user.getIDToken()
                startRequest(url: url, token: token)
            } catch {
                onError(error)
            }
        }
    }
    
    private func startRequest(url: URL, token: String) {
        print("🚀 SSE: Starting request to \(url)")
        print("🔑 SSE: Token prefix: \(token.prefix(20))...")
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue("keep-alive", forHTTPHeaderField: "Connection")
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        activeTask = session.dataTask(with: request)
        activeTask?.resume()
        print("✅ SSE: Request started")
    }
    
    func cancelStream() {
        activeTask?.cancel()
        activeTask = nil
        onChunk = nil
        onEnd = nil
        onError = nil
    }
}

extension SSEClient: URLSessionDataDelegate {
    
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard let string = String(data: data, encoding: .utf8) else { 
            print("❌ SSE: Failed to decode data as UTF-8")
            return 
        }
        
        print("📡 SSE: Received data: \(string.prefix(200))...")
        
        let lines = string.components(separatedBy: "\n")
        var eventType: String?
        
        for line in lines {
            if line.isEmpty { continue }
            
            if line.hasPrefix("event: ") {
                eventType = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
                print("📨 SSE: Event type: \(eventType ?? "nil")")
            } else if line.hasPrefix("data: ") {
                let dataContent = String(line.dropFirst(6))
                print("📦 SSE: Data content: \(dataContent.prefix(100))...")
                
                handleEvent(type: eventType, data: dataContent)
            }
        }
    }
    
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            if (error as NSError).code != NSURLErrorCancelled {
                onError?(error)
            }
        } else {
            // Connection closed cleanly
            onEnd?()
        }
        
        // Cleanup references but keep `onEnd` called if needed
        // We don't nullify callbacks here immediately to ensure onEnd propagates
    }
    
    private func handleEvent(type: String?, data: String) {
        guard let type = type else { 
            print("⚠️ SSE: No event type")
            return 
        }
        
        print("🎯 SSE: Handling event type: \(type)")
        
        switch type {
        case "stream_chunk":
            // Parse JSON data to get chunk content
            // Expected format: {"content": "..."}
            if let jsonData = data.data(using: .utf8),
               let chunk = try? JSONDecoder().decode(StreamChunk.self, from: jsonData) {
                print("✅ SSE: Decoded chunk content: \(chunk.content.prefix(50))...")
                onChunk?(chunk.content)
            } else {
                print("❌ SSE: Failed to decode stream_chunk JSON")
            }
        case "end_stream":
            print("🏁 SSE: Stream ended")
            onEnd?()
            cancelStream() // Stop the connection
        case "error":
            print("❌ SSE: Error event received")
            onError?(SSEError.streamTerminated) // Or parse error message
            cancelStream()
        default:
            print("⚠️ SSE: Unknown event type: \(type)")
            break
        }
    }
}

// Helper model for chunk
struct StreamChunk: Codable {
    let content: String
}

