import Foundation
import AppKit

@MainActor
class CommandHandler: ObservableObject {
    private let baseURL: String
    
    init(port: Int = 8080) {
        self.baseURL = "http://localhost:\(port)"
    }
    
    func handleCommand(_ command: String) async -> (handled: Bool, response: String?) {
        let trimmed = command.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("/") else {
            return (false, nil)
        }
        
        let parts = trimmed.dropFirst().split(separator: " ").map(String.init)
        guard !parts.isEmpty else {
            return (true, "❓ Empty command. Type /help for available commands.")
        }
        
        let cmd = parts[0].lowercased()
        let args = Array(parts.dropFirst())
        
        switch cmd {
        case "help":
            return (true, """
                📋 Available Commands:
                
                /help - Show this help
                /clear - Clear chat history
                /auth status - Check authentication status
                /auth login - Login with Google
                /auth logout - Logout
                /logs - Toggle debug logs display
                /quit or /exit - Exit application
                """)
            
        case "clear":
            // This will be handled by the ChatViewModel
            return (true, nil)
            
        case "auth":
            return await handleAuthCommand(args)
            
        case "logs":
            // This will be handled by the ContentView
            return (true, nil)
            
        case "quit", "exit":
            NSApplication.shared.terminate(nil)
            return (true, nil)
            
        default:
            return (true, "❓ Unknown command: /\(cmd). Type /help for available commands.")
        }
    }
    
    private func handleAuthCommand(_ args: [String]) async -> (handled: Bool, response: String?) {
        guard !args.isEmpty else {
            return (true, "⚠️ Usage: /auth [status|login|logout]")
        }
        
        let subcommand = args[0].lowercased()
        
        switch subcommand {
        case "status":
            return await checkAuthStatus()
            
        case "login":
            return await performLogin()
            
        case "logout":
            return await performLogout()
            
        default:
            return (true, "❓ Unknown auth command. Use: /auth [status|login|logout]")
        }
    }
    
    private func checkAuthStatus() async -> (handled: Bool, response: String?) {
        do {
            let url = URL(string: "\(baseURL)/api/auth/status")!
            let (data, _) = try await URLSession.shared.data(from: url)
            
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let authenticated = json["authenticated"] as? Bool {
                if authenticated {
                    if let userInfo = json["user_info"] as? [String: Any],
                       let email = userInfo["email"] as? String {
                        return (true, "✅ Authenticated as \(email)")
                    }
                    return (true, "✅ Authenticated")
                } else {
                    return (true, "⚠️ Not authenticated. Use /auth login to authenticate.")
                }
            }
            return (true, "❌ Failed to check auth status")
        } catch {
            return (true, "❌ Auth check failed: \(error.localizedDescription)")
        }
    }
    
    private func performLogin() async -> (handled: Bool, response: String?) {
        do {
            let url = URL(string: "\(baseURL)/api/auth/login")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: ["force": false])
            
            let (data, _) = try await URLSession.shared.data(for: request)
            
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                // Check if auth_url is present (need to authenticate)
                if let authURL = json["auth_url"] as? String, !authURL.isEmpty {
                    // Open the auth URL in the default browser
                    if let url = URL(string: authURL) {
                        NSWorkspace.shared.open(url)
                        return (true, """
                            🔐 Opening browser for authentication...
                            Please complete the login in your browser.
                            After authentication, type /auth status to verify.
                            """)
                    }
                } 
                // Check if already authenticated
                else if let status = json["status"] as? [String: Any],
                        let authenticated = status["authenticated"] as? Bool,
                        authenticated == true {
                    if let userInfo = status["user_info"] as? [String: Any],
                       let email = userInfo["email"] as? String {
                        return (true, "✅ Already authenticated as \(email)")
                    }
                    return (true, "✅ Already authenticated!")
                }
                // Check simple success response
                else if let success = json["success"] as? Bool, success == true {
                    if let message = json["message"] as? String {
                        return (true, "✅ \(message)")
                    }
                }
            }
            return (true, "❌ Failed to initiate login")
        } catch {
            return (true, "❌ Login failed: \(error.localizedDescription)")
        }
    }
    
    private func performLogout() async -> (handled: Bool, response: String?) {
        do {
            let url = URL(string: "\(baseURL)/api/auth/logout")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            
            let (_, _) = try await URLSession.shared.data(for: request)
            return (true, "👋 Logged out successfully")
        } catch {
            return (true, "❌ Logout failed: \(error.localizedDescription)")
        }
    }
}