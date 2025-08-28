import Foundation
import Combine
import MetagenAPI

@MainActor
class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isStreaming = false
    @Published var inputText = ""
    @Published var error: String?
    @Published var pendingApproval: ToolApprovalRequest?
    
    private var cancellables = Set<AnyCancellable>()
    let chatService: ChatService
    private let commandHandler: CommandHandler
    
    init() {
        do {
            self.chatService = try ChatService()
        } catch {
            // If initialization fails, create with default port
            self.chatService = try! ChatService(port: 8080)
        }
        self.commandHandler = CommandHandler()
        setupWelcomeMessage()
    }
    
    private func setupWelcomeMessage() {
        let welcome = ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            content: """
            🤖 Welcome to Ambient!
            
            I'm here to help with your tasks. You can ask me anything!
            
            💡 Tips:
            • Type /help to see available commands
            • Use /auth login to connect Google services
            • Type /clear to clear chat history
            """,
            timestamp: Date()
        )
        messages.append(welcome)
    }
    
    func sendMessage(_ content: String) {
        guard !content.isEmpty else { return }
        
        // Check if it's a command
        if content.hasPrefix("/") {
            Task {
                await handleCommand(content)
            }
            // Clear input
            inputText = ""
            return
        }
        
        // Add user message
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            role: .user,
            content: content,
            timestamp: Date()
        )
        messages.append(userMessage)
        
        // Clear input
        inputText = ""
        
        // Start streaming response
        isStreaming = true
        
        Task {
            let response = chatService.sendMessage(content)
            await handleStreamResponse(response)
        }
    }
    
    private func handleCommand(_ command: String) async {
        // Handle special commands that need ChatViewModel access
        if command.lowercased() == "/clear" {
            messages.removeAll()
            setupWelcomeMessage()
            return
        }
        
        let result = await commandHandler.handleCommand(command)
        
        if result.handled {
            if let response = result.response {
                let systemMessage = ChatMessage(
                    id: UUID().uuidString,
                    role: .system,
                    content: response,
                    timestamp: Date()
                )
                messages.append(systemMessage)
            }
        }
    }
    
    private func handleStreamResponse(_ stream: AsyncThrowingStream<ChatEvent, Error>) async {
        // Keep track of current streaming message for agent content
        var currentAgentMessage: ChatMessage? = nil
        var currentAgentMessageIndex: Int? = nil
        var isFirstMessageInTurn = true  // Track if we've shown the first message for this turn
        
        do {
            for try await event in stream {
                switch event {
                case .message(let content):
                    // Agent's actual message content - stream it into current or new message
                    if let index = currentAgentMessageIndex {
                        // Append to existing agent message
                        messages[index].content += content
                    } else {
                        // Create new agent message
                        let agentMessage = ChatMessage(
                            id: UUID().uuidString,
                            role: .assistant,
                            content: content,
                            timestamp: Date(),
                            isFirstInTurn: isFirstMessageInTurn
                        )
                        messages.append(agentMessage)
                        currentAgentMessage = agentMessage
                        currentAgentMessageIndex = messages.count - 1
                        isFirstMessageInTurn = false  // Mark that we've shown the first message
                    }
                    
                case .thinking(_):
                    // Don't show thinking text - we have the dots indicator
                    break
                    
                case .toolCall(let tool):
                    // Reset current agent message tracking since we're showing a tool now
                    currentAgentMessage = nil
                    currentAgentMessageIndex = nil
                    
                    // Format tool call with arguments
                    var toolDisplay = "🔧 \(tool.name)"
                    
                    // Format parameters nicely
                    if !tool.parameters.isEmpty {
                        let params = tool.parameters.compactMap { key, value in
                            if let stringValue = value as? String {
                                return "\(key): \"\(stringValue.prefix(50))\(stringValue.count > 50 ? "..." : "")\""
                            } else if let boolValue = value as? Bool {
                                return "\(key): \(boolValue)"
                            } else if let numValue = value as? NSNumber {
                                return "\(key): \(numValue)"
                            }
                            return nil
                        }.joined(separator: ", ")
                        
                        if !params.isEmpty {
                            toolDisplay += "(\(params))"
                        }
                    } else {
                        toolDisplay += "()"
                    }
                    
                    // Add tool call as a separate system message
                    let toolMessage = ChatMessage(
                        id: UUID().uuidString,
                        role: .system,
                        content: toolDisplay,
                        timestamp: Date(),
                        isFirstInTurn: isFirstMessageInTurn
                    )
                    messages.append(toolMessage)
                    isFirstMessageInTurn = false  // Mark that we've shown the first message
                    
                case .toolStarted(_, _):
                    // Don't show separate "running" status - the tool call is enough
                    break
                    
                case .toolResult(_, _, _):
                    // Don't show result inline - it will be in the agent's message
                    break
                    
                case .toolApproval(let toolCallId, let tool):
                    // Reset current agent message tracking
                    currentAgentMessage = nil
                    currentAgentMessageIndex = nil
                    
                    // Handle tool approval request
                    var approvalText = "⚠️ Approval needed: \(tool.name)"
                    if !tool.parameters.isEmpty {
                        let params = tool.parameters.compactMap { key, value in
                            "\(key): \(value)"
                        }.joined(separator: ", ")
                        approvalText += "(\(params))"
                    }
                    
                    // Add approval request as a separate system message
                    let approvalMessage = ChatMessage(
                        id: UUID().uuidString,
                        role: .system,
                        content: approvalText,
                        timestamp: Date(),
                        isFirstInTurn: isFirstMessageInTurn
                    )
                    messages.append(approvalMessage)
                    isFirstMessageInTurn = false  // Mark that we've shown the first message
                    
                    // Set pending approval
                    pendingApproval = ToolApprovalRequest(
                        id: toolCallId,
                        tool: tool,
                        timestamp: Date()
                    )
                    
                case .usage(_):
                    // Don't show usage inline
                    break
                    
                case .done:
                    isStreaming = false
                    // Reset tracking
                    currentAgentMessage = nil
                    currentAgentMessageIndex = nil
                }
            }
        } catch {
            self.error = error.localizedDescription
            isStreaming = false
        }
    }
    
    func clearMessages() {
        messages.removeAll()
        setupWelcomeMessage()
    }
    
    func approveTool() {
        guard let approval = pendingApproval else { return }
        
        Task {
            do {
                try await chatService.sendToolApprovalResponse(
                    toolId: approval.id,
                    approved: true
                )
                pendingApproval = nil
            } catch {
                self.error = "Failed to approve tool: \(error.localizedDescription)"
            }
        }
    }
    
    func rejectTool(feedback: String? = nil) {
        guard let approval = pendingApproval else { return }
        
        Task {
            do {
                try await chatService.sendToolApprovalResponse(
                    toolId: approval.id,
                    approved: false,
                    feedback: feedback
                )
                pendingApproval = nil
            } catch {
                self.error = "Failed to reject tool: \(error.localizedDescription)"
            }
        }
    }
}

struct ChatMessage: Identifiable {
    let id: String
    let role: MessageRole
    var content: String
    let timestamp: Date
    var isFirstInTurn: Bool = false  // Track if this is the first message in a turn
}

enum MessageRole {
    case user
    case assistant
    case system
}

struct ToolApprovalRequest: Identifiable {
    let id: String
    let tool: ToolUse
    let timestamp: Date
}
