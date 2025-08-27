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
        let assistantMessage = ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            content: "",
            timestamp: Date()
        )
        messages.append(assistantMessage)
        let messageIndex = messages.count - 1
        
        var toolCallsSection = ""
        var contentSection = ""
        var hasReceivedContent = false
        
        do {
            for try await event in stream {
                switch event {
                case .message(let content):
                    // Agent's actual message content
                    hasReceivedContent = true
                    contentSection += content
                    
                    // Update display: show tools (if any) followed by content
                    if !toolCallsSection.isEmpty {
                        messages[messageIndex].content = toolCallsSection + "\n\n" + contentSection
                    } else {
                        messages[messageIndex].content = contentSection
                    }
                    
                case .thinking(_):
                    // Don't show thinking text - we have the dots indicator
                    break
                    
                case .toolCall(let tool):
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
                    
                    // Add to tools section
                    if !toolCallsSection.isEmpty {
                        toolCallsSection += "\n"
                    }
                    toolCallsSection += toolDisplay
                    
                    // Update display
                    messages[messageIndex].content = toolCallsSection
                    
                case .toolStarted(_, _):
                    // Don't show separate "running" status - the tool call is enough
                    break
                    
                case .toolResult(_, _, _):
                    // Don't show result inline - it will be in the agent's message
                    break
                    
                case .toolApproval(let toolCallId, let tool):
                    // Handle tool approval request
                    var approvalText = "⚠️ Approval needed: \(tool.name)"
                    if !tool.parameters.isEmpty {
                        let params = tool.parameters.compactMap { key, value in
                            "\(key): \(value)"
                        }.joined(separator: ", ")
                        approvalText += "(\(params))"
                    }
                    
                    if !toolCallsSection.isEmpty {
                        toolCallsSection += "\n"
                    }
                    toolCallsSection += approvalText
                    messages[messageIndex].content = toolCallsSection
                    
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
                    // Final cleanup: ensure we show the final content
                    if hasReceivedContent {
                        if !toolCallsSection.isEmpty && !contentSection.isEmpty {
                            messages[messageIndex].content = toolCallsSection + "\n\n" + contentSection
                        } else if !contentSection.isEmpty {
                            messages[messageIndex].content = contentSection
                        }
                    }
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
