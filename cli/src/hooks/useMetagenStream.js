/**
 * Hook for managing Metagen streaming chat interactions
 * Uses the generated OpenAPI TypeScript client
 */
import { useState, useRef, useCallback } from 'react';
import { MetagenStreamingClient, ChatService, AuthenticationService, ToolsService, SystemService, MemoryService, ApprovalDecision, MessageType, OpenAPI } from '../../../api/ts/src/index.js';
// Configure the API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';
// Type guards for each message type
function isUserMessage(msg) {
    return msg.type === MessageType.USER;
}
function isAgentMessage(msg) {
    return msg.type === MessageType.AGENT;
}
function isSystemMessage(msg) {
    return msg.type === MessageType.SYSTEM;
}
function isThinkingMessage(msg) {
    return msg.type === MessageType.THINKING;
}
function isToolCallMessage(msg) {
    return msg.type === MessageType.TOOL_CALL;
}
function isToolStartedMessage(msg) {
    return msg.type === MessageType.TOOL_STARTED;
}
function isToolResultMessage(msg) {
    return msg.type === MessageType.TOOL_RESULT;
}
function isToolErrorMessage(msg) {
    return msg.type === MessageType.TOOL_ERROR;
}
function isApprovalRequestMessage(msg) {
    return msg.type === MessageType.APPROVAL_REQUEST;
}
function isApprovalResponseMessage(msg) {
    return msg.type === MessageType.APPROVAL_RESPONSE;
}
function isErrorMessage(msg) {
    return msg.type === MessageType.ERROR;
}
function isUsageMessage(msg) {
    return msg.type === MessageType.USAGE;
}
export function useMetagenStream(options = {}) {
    const { autoApproveTools = false } = options;
    const [messages, setMessages] = useState([]);
    const [isResponding, setIsResponding] = useState(false);
    const [sessionId] = useState(() => crypto.randomUUID());
    const [showToolResults, setShowToolResults] = useState(false);
    const [pendingApproval, setPendingApproval] = useState(null);
    const streamingClient = useRef(null);
    const abortControllerRef = useRef(null);
    // Initialize streaming client
    if (!streamingClient.current) {
        streamingClient.current = new MetagenStreamingClient(OpenAPI.BASE);
    }
    const addMessage = useCallback((sender, content, type = 'agent', metadata) => {
        const message = {
            id: `${Date.now()}-${Math.random()}`,
            type,
            content,
            timestamp: new Date(),
            metadata,
            expanded: false
        };
        setMessages(prev => [...prev, message]);
    }, []);
    const clearMessages = useCallback(() => {
        setMessages([]);
    }, []);
    const toggleToolResults = useCallback(() => {
        setShowToolResults(prev => !prev);
    }, []);
    const toggleMessageExpanded = useCallback((messageId) => {
        setMessages(prev => prev.map(msg => msg.id === messageId ? { ...msg, expanded: !msg.expanded } : msg));
    }, []);
    const handleSlashCommand = useCallback(async (command) => {
        const parts = command.slice(1).split(' ');
        const cmd = parts[0].toLowerCase();
        const args = parts.slice(1);
        switch (cmd) {
            case 'help':
                addMessage('system', '📋 Available Commands:\n\n/help - Show this help\n/clear - Clear chat UI\n/clear-db - Clear database history\n/auth status - Check authentication\n/auth login - Login with Google\n/auth logout - Logout\n/tools - List available tools\n/system health - Check system status\n/system info - Get system information\n/toggle-results - Toggle tool results display\n/quit or /exit - Exit chat', 'system');
                break;
            case 'toggle-results':
                toggleToolResults();
                addMessage('system', `🔍 Tool results display: ${!showToolResults ? 'ON' : 'OFF'}`, 'system');
                break;
            case 'clear':
                clearMessages();
                addMessage('system', '🧹 Chat UI cleared!', 'system');
                break;
            case 'clear-db':
                try {
                    await MemoryService.clearHistoryApiMemoryClearPost();
                    addMessage('system', '🗄️ Database history cleared! Agent will have fresh context.', 'system');
                }
                catch (error) {
                    addMessage('system', `❌ Failed to clear database: ${error instanceof Error ? error.message : String(error)}`, 'error');
                }
                break;
            case 'auth':
                if (args[0] === 'status') {
                    try {
                        const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
                        if (auth.authenticated) {
                            addMessage('system', `✅ Authenticated${auth.user_info?.email ? ` as ${auth.user_info.email}` : ''}`, 'system');
                        }
                        else {
                            addMessage('system', '⚠️  Not authenticated. Use "/auth login" to authenticate.', 'system');
                        }
                    }
                    catch (error) {
                        addMessage('system', `❌ Auth check failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
                    }
                }
                else if (args[0] === 'login') {
                    try {
                        const response = await AuthenticationService.loginApiAuthLoginPost({
                            requestBody: { force: false }
                        });
                        if (response.auth_url) {
                            addMessage('system', `🔐 ${response.message || 'Login required'}\n🌐 Open: ${response.auth_url}`, 'system');
                        }
                        else {
                            addMessage('system', `✅ ${response.message || 'Already authenticated'}`, 'system');
                        }
                    }
                    catch (error) {
                        addMessage('system', `❌ Login failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
                    }
                }
                else if (args[0] === 'logout') {
                    try {
                        await AuthenticationService.logoutApiAuthLogoutPost();
                        addMessage('system', '👋 Logged out successfully', 'system');
                    }
                    catch (error) {
                        addMessage('system', `❌ Logout failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
                    }
                }
                break;
            case 'tools':
                try {
                    const tools = await ToolsService.getToolsApiToolsGet();
                    const toolsList = tools.tools.map((tool, i) => `  ${i + 1}. ${tool.name} - ${tool.description}`).join('\n');
                    addMessage('system', `🔧 Available Tools (${tools.count}):\n\n${toolsList}`, 'system');
                }
                catch (error) {
                    addMessage('system', `❌ Failed to fetch tools: ${error instanceof Error ? error.message : String(error)}`, 'error');
                }
                break;
            case 'system':
                if (args[0] === 'health') {
                    try {
                        await SystemService.healthCheckApiSystemHealthGet();
                        addMessage('system', '🏥 System Health: HEALTHY', 'system');
                    }
                    catch (error) {
                        addMessage('system', `❌ System Health: UNHEALTHY - ${error instanceof Error ? error.message : String(error)}`, 'error');
                    }
                }
                else if (args[0] === 'info') {
                    try {
                        const info = await SystemService.getSystemInfoApiSystemInfoGet();
                        const infoText = `Agent: ${info.agent_name}\nModel: ${info.model}\nTools: ${info.tool_count}\nMemory: ${info.memory_path}`;
                        addMessage('system', `ℹ️ System Information:\n\n${infoText}`, 'system');
                    }
                    catch (error) {
                        addMessage('system', `❌ Failed to get system info: ${error instanceof Error ? error.message : String(error)}`, 'error');
                    }
                }
                break;
            default:
                addMessage('system', `❓ Unknown command: /${cmd}. Type "/help" for available commands.`, 'error');
        }
    }, [addMessage, clearMessages, showToolResults, toggleToolResults]);
    const sendMessage = useCallback(async (message) => {
        if (!message.trim() || isResponding)
            return;
        const userMessage = message.trim();
        // Handle commands
        if (userMessage.startsWith('/')) {
            await handleSlashCommand(userMessage);
            return;
        }
        // Cancel any previous request
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        // Create new abort controller for this request
        abortControllerRef.current = new AbortController();
        setIsResponding(true);
        // Add user message
        addMessage('user', userMessage, 'user');
        try {
            // Create chat request
            // TODO: Add auto_approve_tools to backend API
            const chatRequest = {
                message: userMessage,
                session_id: sessionId
            };
            // Stream the response
            let currentAgentMessageId = null;
            let currentAgentContent = '';
            for await (const sseMessage of streamingClient.current.chatStream(chatRequest)) {
                // Check if aborted
                if (abortControllerRef.current?.signal.aborted) {
                    break;
                }
                // Handle different message types - preserve exact stream order
                if (isAgentMessage(sseMessage)) {
                    currentAgentContent += sseMessage.content;
                    if (!currentAgentMessageId) {
                        // Start a new agent message
                        currentAgentMessageId = `agent-${Date.now()}-${Math.random()}`;
                        setMessages(prev => [...prev, {
                                id: currentAgentMessageId,
                                type: 'agent',
                                content: currentAgentContent,
                                timestamp: new Date(),
                                isStreaming: true,
                                metadata: {}
                            }]);
                    }
                    else {
                        // Update the existing streaming message
                        setMessages(prev => prev.map(msg => msg.id === currentAgentMessageId
                            ? { ...msg, content: currentAgentContent }
                            : msg));
                    }
                    // Check if this is the final message
                    if (sseMessage.final) {
                        // Finalize the message
                        setMessages(prev => prev.map(msg => msg.id === currentAgentMessageId
                            ? { ...msg, isStreaming: false, metadata: { ...msg.metadata, final: true } }
                            : msg));
                        currentAgentMessageId = null;
                        currentAgentContent = '';
                        break;
                    }
                }
                else {
                    // If we have a streaming agent message, finalize it first
                    if (currentAgentMessageId) {
                        setMessages(prev => prev.map(msg => msg.id === currentAgentMessageId
                            ? { ...msg, isStreaming: false }
                            : msg));
                        currentAgentMessageId = null;
                        currentAgentContent = '';
                    }
                    // Add non-agent messages in order
                    if (isThinkingMessage(sseMessage)) {
                        // Don't show thinking messages - they clutter the output
                        // addMessage('system', `🤔 ${sseMessage.content}`, 'thinking', {});
                    }
                    else if (isToolCallMessage(sseMessage)) {
                        // Show tool calls with arguments preview
                        for (const toolCall of sseMessage.tool_calls) {
                            const argsPreview = toolCall.tool_args
                                ? JSON.stringify(toolCall.tool_args, null, 2)
                                : '';
                            // Create a short preview of arguments for the collapsed view
                            const shortArgs = toolCall.tool_args
                                ? `(${Object.keys(toolCall.tool_args).map(k => `${k}: ${JSON.stringify(toolCall.tool_args[k])}`).join(', ').substring(0, 50)}...)`
                                : '()';
                            const toolInfo = `${toolCall.tool_name}${shortArgs}`;
                            addMessage('system', toolInfo, 'tool_call', {
                                tool_id: toolCall.tool_id,
                                tool_name: toolCall.tool_name,
                                args: toolCall.tool_args,
                                argsPreview
                            });
                        }
                    }
                    else if (isToolStartedMessage(sseMessage)) {
                        // Skip tool started messages to reduce clutter
                        // addMessage('system', `▶️ Started: ${sseMessage.tool_name}`, 'tool_started', { tool_id: sseMessage.tool_id });
                    }
                    else if (isToolResultMessage(sseMessage)) {
                        // Store full result in metadata but don't show unless it's an error
                        const fullResult = typeof sseMessage.result === 'string'
                            ? sseMessage.result
                            : JSON.stringify(sseMessage.result, null, 2);
                        // Only add a message for debugging - will be hidden by default
                        // Tool results are collapsed under their tool calls
                        // We don't show them unless explicitly expanded
                    }
                    else if (isToolErrorMessage(sseMessage)) {
                        // Always show tool errors prominently
                        addMessage('error', `❌ Tool error in ${sseMessage.tool_name}: ${sseMessage.error}`, 'tool_error', {
                            tool_id: sseMessage.tool_id,
                            tool_name: sseMessage.tool_name,
                            error: sseMessage.error
                        });
                    }
                    else if (isErrorMessage(sseMessage)) {
                        addMessage('system', `❌ Error: ${sseMessage.error}`, 'error', sseMessage.details || {});
                        break;
                    }
                    else if (isApprovalRequestMessage(sseMessage)) {
                        if (autoApproveTools) {
                            // Auto-approve tools in non-interactive mode
                            const approvalMessage = {
                                type: MessageType.APPROVAL_RESPONSE,
                                timestamp: new Date().toISOString(),
                                agent_id: sseMessage.agent_id || 'USER',
                                session_id: sessionId,
                                tool_id: sseMessage.tool_id,
                                decision: ApprovalDecision.APPROVED,
                                feedback: 'Auto-approved'
                            };
                            // Send approval immediately
                            ChatService.handleApprovalResponseApiChatApprovalResponsePost({
                                requestBody: approvalMessage
                            }).catch(error => {
                                addMessage('system', `❌ Failed to auto-approve tool: ${error instanceof Error ? error.message : String(error)}`, 'error');
                            });
                            const toolName = sseMessage.tool_name || 'Unknown tool';
                            addMessage('system', `✅ Auto-approved: ${toolName}`, 'approval_response');
                        }
                        else {
                            // Interactive mode - wait for user approval
                            setPendingApproval(sseMessage);
                            const toolName = sseMessage.tool_name || 'Unknown tool';
                            addMessage('system', `🔐 Tool requires approval: ${toolName}`, 'approval_request', { tool_id: sseMessage.tool_id });
                        }
                    }
                }
            }
        }
        catch (error) {
            if (error instanceof Error && error.name === 'AbortError') {
                addMessage('system', '⚠️ Request cancelled', 'system');
            }
            else {
                addMessage('system', `❌ Error: ${error instanceof Error ? error.message : String(error)}`, 'error');
            }
        }
        finally {
            setIsResponding(false);
            abortControllerRef.current = null;
        }
    }, [isResponding, addMessage, handleSlashCommand, sessionId]);
    const handleToolDecision = useCallback(async (approved, feedback) => {
        if (!pendingApproval || !isApprovalRequestMessage(pendingApproval))
            return;
        try {
            const approvalMessage = {
                type: MessageType.APPROVAL_RESPONSE,
                timestamp: new Date().toISOString(),
                agent_id: pendingApproval.agent_id || 'USER',
                session_id: sessionId,
                tool_id: pendingApproval.tool_id,
                decision: approved ? ApprovalDecision.APPROVED : ApprovalDecision.REJECTED,
                feedback: feedback
            };
            await ChatService.handleApprovalResponseApiChatApprovalResponsePost({
                requestBody: approvalMessage
            });
            // Clear pending approval
            setPendingApproval(null);
            // Add feedback to UI
            const decision = approved ? '✅ Approved' : '❌ Rejected';
            const message = feedback ? `${decision}: ${feedback}` : decision;
            addMessage('system', message, 'approval_response');
        }
        catch (error) {
            addMessage('system', `❌ Failed to send tool decision: ${error instanceof Error ? error.message : String(error)}`, 'error');
        }
    }, [pendingApproval, sessionId, addMessage]);
    return {
        messages,
        isResponding,
        sessionId,
        showToolResults,
        toggleToolResults,
        sendMessage,
        addMessage,
        clearMessages,
        handleSlashCommand,
        pendingApproval,
        handleToolDecision,
        toggleMessageExpanded
    };
}
