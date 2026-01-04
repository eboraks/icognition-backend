//
//  HTMLMessageView.swift
//  iso-app
//
//  Created by AI Assistant on 12/5/25.
//

import SwiftUI
import WebKit

struct HTMLMessageView: UIViewRepresentable {
    let htmlContent: String
    let isCurrentUser: Bool
    
    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.navigationDelegate = context.coordinator
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false // Let the chat view handle scrolling
        webView.scrollView.bounces = false
        webView.scrollView.showsVerticalScrollIndicator = false
        webView.scrollView.showsHorizontalScrollIndicator = false
        return webView
    }
    
    func updateUIView(_ webView: WKWebView, context: Context) {
        let textColor = isCurrentUser ? "#FFFFFF" : "#000000"
        let linkColor = isCurrentUser ? "#E0E0E0" : "#007AFF"
        
        let htmlString = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    font-size: 16px;
                    line-height: 1.4;
                    color: \(textColor);
                    margin: 0;
                    padding: 0;
                    word-wrap: break-word;
                }
                img {
                    max-width: 100%;
                    height: auto;
                    border-radius: 8px;
                }
                a {
                    color: \(linkColor);
                    text-decoration: underline;
                }
                p {
                    margin-bottom: 8px;
                }
                p:last-child {
                    margin-bottom: 0;
                }
                ul, ol {
                    margin: 8px 0;
                    padding-left: 20px;
                }
                li {
                    margin: 4px 0;
                }
                ul {
                    list-style-type: disc;
                }
                ol {
                    list-style-type: decimal;
                }
                strong, b {
                    font-weight: 600;
                }
                em, i {
                    font-style: italic;
                }
                code {
                    background-color: rgba(0,0,0,0.1);
                    padding: 2px 4px;
                    border-radius: 4px;
                    font-family: 'Menlo', monospace;
                    font-size: 0.9em;
                }
                pre {
                    background-color: rgba(0,0,0,0.05);
                    padding: 8px;
                    border-radius: 8px;
                    overflow-x: auto;
                }
                blockquote {
                    border-left: 3px solid rgba(0,0,0,0.2);
                    padding-left: 12px;
                    margin: 8px 0;
                    font-style: italic;
                }
            </style>
        </head>
        <body>
        \(htmlContent)
        </body>
        </html>
        """
        webView.loadHTMLString(htmlString, baseURL: nil)
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if navigationAction.navigationType == .linkActivated {
                if let url = navigationAction.request.url {
                    UIApplication.shared.open(url)
                    decisionHandler(.cancel)
                    return
                }
            }
            decisionHandler(.allow)
        }
    }
}

