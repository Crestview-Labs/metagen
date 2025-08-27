import Foundation
import MetagenAPI
import Combine

@MainActor
class ChatService: ObservableObject {
    private let streamingClient: MetagenStreamingClient
    private var currentSessionId: String?
    @Published var logs: String = ""
    private let baseURL: String
    
    init(port: Int = 8080) throws {
        // Configure the streaming client
        self.baseURL = "http://localhost:\(port)"
        self.streamingClient = try MetagenStreamingClient(baseURL: self.baseURL)
        self.currentSessionId = UUID().uuidString
    }
    
    private func log(_ message: String) {
        let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        logs += "[\(timestamp)] \(message)\n"
        
        // Keep only last 500 lines
        let lines = logs.components(separatedBy: "\n")
        if lines.count > 500 {
            logs = lines.suffix(500).joined(separator: "\n")
        }
    }
    
    func sendMessage(_ content: String) -> AsyncThrowingStream<ChatEvent, Error> {
        // Create or reuse session
        if currentSessionId == nil {
            currentSessionId = UUID().uuidString
        }
        
        let sessionId = currentSessionId!
        log("📤 Sending message to backend - Session: \(sessionId)")
        
        let stream = AsyncThrowingStream<ChatEvent, Error> { continuation in
            Task {
                do {
                    // Use the streaming client
                    let stream = streamingClient.chatStream(message: content, sessionId: sessionId)
                    
                    for try await event in stream {
                        // Parse the event based on type
                        if let dict = event as? [String: Any] {
                            log("📥 Received event: \(String(describing: dict["type"]))")
                            
                            if let type = dict["type"] as? String {
                                switch type {
                                case "agent":
                                    if let content = dict["content"] as? String {
                                        log("💬 Agent message: \(content.prefix(100))...")
                                        continuation.yield(.message(content))
                                    }
                                    // Check if this is the final message
                                    if let final = dict["final"] as? Bool, final == true {
                                        log("✅ Final message received, completing stream")
                                        continuation.yield(.done)
                                        continuation.finish()
                                        return
                                    }
                                    
                                case "thinking":
                                    let content = dict["content"] as? String
                                    log("🤔 Thinking: \(content ?? "...")")
                                    continuation.yield(.thinking(content))
                                    
                                case "tool_call":
                                    // Backend sends tool_calls array with tool_id, tool_name, tool_args
                                    if let toolCalls = dict["tool_calls"] as? [[String: Any]] {
                                        for toolCall in toolCalls {
                                            let toolName = toolCall["tool_name"] as? String ?? "unknown"
                                            let toolArgs = toolCall["tool_args"] as? [String: Any] ?? [:]
                                            log("🔧 Tool call: \(toolName) with args: \(toolArgs)")
                                            continuation.yield(.toolCall(ToolUse(name: toolName, parameters: toolArgs)))
                                        }
                                    }
                                    
                                case "tool_started":
                                    let name = dict["tool_name"] as? String ?? "unknown"
                                    let id = dict["tool_id"] as? String ?? ""
                                    log("🚀 Tool started: \(name)")
                                    continuation.yield(.toolStarted(name: name, id: id))
                                    
                                case "tool_result":
                                    let name = dict["tool_name"] as? String ?? "unknown"
                                    let id = dict["tool_id"] as? String ?? ""
                                    let result = dict["result"] as? String
                                    log("📊 Tool result: \(name)")
                                    continuation.yield(.toolResult(name: name, id: id, result: result))
                                    
                                case "approval_request":
                                    if let toolId = dict["tool_id"] as? String,
                                       let toolName = dict["tool_name"] as? String,
                                       let toolArgs = dict["tool_args"] as? [String: Any] {
                                        log("⚠️ Tool approval request: \(toolName)")
                                        let tool = ToolUse(name: toolName, parameters: toolArgs)
                                        continuation.yield(.toolApproval(toolCallId: toolId, tool: tool))
                                    }
                                    
                                case "usage":
                                    log("📊 Usage stats received")
                                    continuation.yield(.usage(usage: dict))
                                    
                                case "complete":
                                    log("✅ Complete signal received")
                                    continuation.yield(.done)
                                    continuation.finish()
                                    return
                                    
                                case "error":
                                    if let error = dict["error"] as? String {
                                        log("❌ Error from backend: \(error)")
                                        continuation.finish(throwing: ChatError.serverError(0))
                                    }
                                    
                                default:
                                    log("⚠️ Unknown message type: \(type)")
                                    break
                                }
                            }
                        }
                    }
                    
                    log("📭 Stream ended naturally")
                    continuation.finish()
                } catch {
                    log("❌ Stream error: \(error)")
                    continuation.finish(throwing: error)
                }
            }
        }
        
        return stream
    }
    
    func sendToolApprovalResponse(toolId: String, approved: Bool, feedback: String? = nil) async throws {
        guard let sessionId = currentSessionId else {
            throw ChatError.unexpectedResponse
        }
        
        let url = URL(string: "\(baseURL)/api/chat/approval-response")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "session_id": sessionId,
            "tool_id": toolId,
            "decision": approved ? "approved" : "rejected",
            "feedback": feedback as Any
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (_, response) = try await URLSession.shared.data(for: request)
        
        if let httpResponse = response as? HTTPURLResponse {
            if httpResponse.statusCode != 200 {
                throw ChatError.serverError(httpResponse.statusCode)
            }
        }
        
        log(approved ? "✅ Tool approved: \(toolId)" : "❌ Tool rejected: \(toolId)")
    }
}

enum ChatEvent {
    case message(String)
    case thinking(String?)
    case toolCall(ToolUse)
    case toolStarted(name: String, id: String)
    case toolResult(name: String, id: String, result: String?)
    case toolApproval(toolCallId: String, tool: ToolUse)
    case usage(usage: [String: Any])
    case done
}

struct ToolUse {
    let name: String
    let parameters: [String: Any]
    
    init(from dict: [String: Any]) {
        self.name = dict["name"] as? String ?? ""
        // Backend sends "arguments" for tool calls
        self.parameters = dict["arguments"] as? [String: Any] ?? dict["parameters"] as? [String: Any] ?? [:]
    }
    
    init(name: String, parameters: [String: Any]) {
        self.name = name
        self.parameters = parameters
    }
}

enum ChatError: LocalizedError {
    case unexpectedResponse
    case serverError(Int)
    
    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .serverError(let code):
            return "Server error: \(code)"
        }
    }
}