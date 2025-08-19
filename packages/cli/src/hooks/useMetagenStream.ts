/**
 * Hook for managing Metagen streaming chat interactions
 * Uses the generated OpenAPI TypeScript client
 */

import { useState, useRef, useCallback } from 'react';
import { 
  MetagenStreamingClient,
  ChatService,
  AuthenticationService,
  ToolsService,
  SystemService,
  MemoryService,
  type ChatRequest,
  type ApprovalResponseMessage,
  type SSEMessage,
  ApprovalDecision,
  MessageType,
  OpenAPI
} from '../../../../api/ts/src/index.js';

// Configure the API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

// Import message types for type guards
import type {
  UserMessage,
  AgentMessage,
  SystemMessage,
  ThinkingMessage,
  ToolCallMessage,
  ToolStartedMessage,
  ToolResultMessage,
  ToolErrorMessage,
  ApprovalRequestMessage,
  ErrorMessage,
  UsageMessage
} from '../../../../api/ts/src/index.js';

// Type guards for each message type
function isUserMessage(msg: SSEMessage): msg is UserMessage {
  return msg.type === MessageType.USER;
}

function isAgentMessage(msg: SSEMessage): msg is AgentMessage {
  return msg.type === MessageType.AGENT;
}

function isSystemMessage(msg: SSEMessage): msg is SystemMessage {
  return msg.type === MessageType.SYSTEM;
}

function isThinkingMessage(msg: SSEMessage): msg is ThinkingMessage {
  return msg.type === MessageType.THINKING;
}

function isToolCallMessage(msg: SSEMessage): msg is ToolCallMessage {
  return msg.type === MessageType.TOOL_CALL;
}

function isToolStartedMessage(msg: SSEMessage): msg is ToolStartedMessage {
  return msg.type === MessageType.TOOL_STARTED;
}

function isToolResultMessage(msg: SSEMessage): msg is ToolResultMessage {
  return msg.type === MessageType.TOOL_RESULT;
}

function isToolErrorMessage(msg: SSEMessage): msg is ToolErrorMessage {
  return msg.type === MessageType.TOOL_ERROR;
}

function isApprovalRequestMessage(msg: SSEMessage): msg is ApprovalRequestMessage {
  return msg.type === MessageType.APPROVAL_REQUEST;
}

function isApprovalResponseMessage(msg: SSEMessage): msg is ApprovalResponseMessage {
  return msg.type === MessageType.APPROVAL_RESPONSE;
}

function isErrorMessage(msg: SSEMessage): msg is ErrorMessage {
  return msg.type === MessageType.ERROR;
}

function isUsageMessage(msg: SSEMessage): msg is UsageMessage {
  return msg.type === MessageType.USAGE;
}

// Message type for UI display
export type UIMessageType = 'user' | 'agent' | 'system' | 'error' | 'thinking' | 'tool_call' | 
  'tool_started' | 'tool_result' | 'tool_error' | 'approval_request' | 'approval_response';

export interface StreamMessage {
  id: string;
  type: UIMessageType;
  content: string;
  timestamp: Date;
  metadata?: Record<string, any>;
}

export interface UseMetagenStreamReturn {
  messages: StreamMessage[];
  isResponding: boolean;
  sessionId: string;
  showToolResults: boolean;
  toggleToolResults: () => void;
  sendMessage: (message: string) => Promise<void>;
  addMessage: (sender: string, content: string, type?: UIMessageType, metadata?: Record<string, any>) => void;
  clearMessages: () => void;
  handleSlashCommand: (command: string) => Promise<void>;
  pendingApproval: any | null;
  handleToolDecision: (approved: boolean, feedback?: string) => Promise<void>;
}

export function useMetagenStream(): UseMetagenStreamReturn {
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [isResponding, setIsResponding] = useState(false);
  const [sessionId] = useState<string>(() => crypto.randomUUID());
  const [showToolResults, setShowToolResults] = useState(true);
  const [pendingApproval, setPendingApproval] = useState<SSEMessage | null>(null);
  const streamingClient = useRef<MetagenStreamingClient | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Initialize streaming client
  if (!streamingClient.current) {
    streamingClient.current = new MetagenStreamingClient(OpenAPI.BASE);
  }

  const addMessage = useCallback((sender: string, content: string, type: UIMessageType = 'agent', metadata?: Record<string, any>) => {
    const message: StreamMessage = {
      id: `${Date.now()}-${Math.random()}`,
      type,
      content,
      timestamp: new Date(),
      metadata
    };
    setMessages(prev => [...prev, message]);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const toggleToolResults = useCallback(() => {
    setShowToolResults(prev => !prev);
  }, []);

  const handleSlashCommand = useCallback(async (command: string) => {
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
        } catch (error) {
          addMessage('system', `❌ Failed to clear database: ${error instanceof Error ? error.message : String(error)}`, 'error');
        }
        break;
        
      case 'auth':
        if (args[0] === 'status') {
          try {
            const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
            if (auth.authenticated) {
              addMessage('system', `✅ Authenticated${auth.user_info?.email ? ` as ${auth.user_info.email}` : ''}`, 'system');
            } else {
              addMessage('system', '⚠️  Not authenticated. Use "/auth login" to authenticate.', 'system');
            }
          } catch (error) {
            addMessage('system', `❌ Auth check failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
          }
        } else if (args[0] === 'login') {
          try {
            const response = await AuthenticationService.loginApiAuthLoginPost({
              requestBody: { force: false }
            });
            if (response.auth_url) {
              addMessage('system', `🔐 ${response.message || 'Login required'}\n🌐 Open: ${response.auth_url}`, 'system');
            } else {
              addMessage('system', `✅ ${response.message || 'Already authenticated'}`, 'system');
            }
          } catch (error) {
            addMessage('system', `❌ Login failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
          }
        } else if (args[0] === 'logout') {
          try {
            await AuthenticationService.logoutApiAuthLogoutPost();
            addMessage('system', '👋 Logged out successfully', 'system');
          } catch (error) {
            addMessage('system', `❌ Logout failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
          }
        }
        break;
        
      case 'tools':
        try {
          const tools = await ToolsService.getToolsApiToolsGet();
          const toolsList = tools.tools.map((tool, i) => `  ${i + 1}. ${tool.name} - ${tool.description}`).join('\n');
          addMessage('system', `🔧 Available Tools (${tools.count}):\n\n${toolsList}`, 'system');
        } catch (error) {
          addMessage('system', `❌ Failed to fetch tools: ${error instanceof Error ? error.message : String(error)}`, 'error');
        }
        break;
        
      case 'system':
        if (args[0] === 'health') {
          try {
            await SystemService.healthCheckApiSystemHealthGet();
            addMessage('system', '🏥 System Health: HEALTHY', 'system');
          } catch (error) {
            addMessage('system', `❌ System Health: UNHEALTHY - ${error instanceof Error ? error.message : String(error)}`, 'error');
          }
        } else if (args[0] === 'info') {
          try {
            const info = await SystemService.getSystemInfoApiSystemInfoGet();
            const infoText = `Agent: ${info.agent_name}\nModel: ${info.model}\nTools: ${info.tool_count}\nMemory: ${info.memory_path}`;
            addMessage('system', `ℹ️ System Information:\n\n${infoText}`, 'system');
          } catch (error) {
            addMessage('system', `❌ Failed to get system info: ${error instanceof Error ? error.message : String(error)}`, 'error');
          }
        }
        break;
        
      default:
        addMessage('system', `❓ Unknown command: /${cmd}. Type "/help" for available commands.`, 'error');
    }
  }, [addMessage, clearMessages, showToolResults, toggleToolResults]);

  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || isResponding) return;

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
      const chatRequest: ChatRequest = {
        message: userMessage,
        session_id: sessionId
      };

      // Stream the response
      let currentMessage = '';
      let messageId: string | null = null;
      let hasStartedResponse = false;
      
      for await (const sseMessage of streamingClient.current!.chatStream(chatRequest)) {
        // Check if aborted
        if (abortControllerRef.current?.signal.aborted) {
          break;
        }

        // Map SSE message types to UI message types
        const mapMessageType = (type: MessageType): UIMessageType => {
          switch (type) {
            case MessageType.AGENT: return 'agent';
            case MessageType.SYSTEM: return 'system';
            case MessageType.THINKING: return 'thinking';
            case MessageType.TOOL_CALL: return 'tool_call';
            case MessageType.TOOL_RESULT: return 'tool_result';
            case MessageType.TOOL_ERROR: return 'tool_error';
            case MessageType.ERROR: return 'error';
            case MessageType.APPROVAL_REQUEST: return 'approval_request';
            case MessageType.APPROVAL_RESPONSE: return 'approval_response';
            case MessageType.TOOL_STARTED: return 'tool_started';
            case MessageType.USER: return 'user';
            case MessageType.USAGE: return 'agent'; // Map usage to agent for UI
            default: return 'agent';
          }
        };

        const uiType = mapMessageType(sseMessage.type!);
        
        // Handle different message types using type guards
        if (isAgentMessage(sseMessage)) {
          // Accumulate agent messages for smooth display
          if (!hasStartedResponse) {
            hasStartedResponse = true;
            addMessage('system', '└─ response:', 'system');
          }
          
          currentMessage += sseMessage.content;
          
          if (!messageId) {
            // Create new message for first chunk
            messageId = `msg-${Date.now()}-${Math.random()}`;
            setMessages(prev => [...prev, {
              id: messageId!,
              type: 'agent',
              content: currentMessage,
              timestamp: new Date(),
              metadata: {}
            }]);
          } else {
            // Update existing message
            setMessages(prev => prev.map(msg => 
              msg.id === messageId 
                ? { ...msg, content: currentMessage }
                : msg
            ));
          }
          
          // Check if this is the final message
          if (sseMessage.final) {
            currentMessage = '';
            messageId = null;
            hasStartedResponse = false;
            break;
          }
        } else if (isThinkingMessage(sseMessage)) {
          addMessage('system', sseMessage.content, 'thinking', {});
        } else if (isToolCallMessage(sseMessage)) {
          // Handle multiple tool calls
          for (const toolCall of sseMessage.tool_calls) {
            const toolInfo = `🔧 Calling tool: ${toolCall.tool_name}`;
            addMessage('agent', toolInfo, 'tool_call', { tool_id: toolCall.tool_id, args: toolCall.tool_args });
          }
          // Reset message accumulation after tool calls
          currentMessage = '';
          messageId = null;
          hasStartedResponse = false;
        } else if (isToolStartedMessage(sseMessage)) {
          const toolInfo = `▶️ Started: ${sseMessage.tool_name}`;
          addMessage('system', toolInfo, 'tool_started', { tool_id: sseMessage.tool_id });
        } else if (isToolResultMessage(sseMessage) && showToolResults) {
          const formattedResult = typeof sseMessage.result === 'string' 
            ? sseMessage.result 
            : JSON.stringify(sseMessage.result, null, 2);
          addMessage('system', `📊 Tool result from ${sseMessage.tool_name}:\n${formattedResult}`, 'tool_result', { tool_id: sseMessage.tool_id });
        } else if (isToolErrorMessage(sseMessage)) {
          addMessage('system', `❌ Tool error in ${sseMessage.tool_name}: ${sseMessage.error}`, 'tool_error', { tool_id: sseMessage.tool_id });
        } else if (isErrorMessage(sseMessage)) {
          addMessage('system', `❌ Error: ${sseMessage.error}`, 'error', sseMessage.details || {});
          break;
        } else if (isApprovalRequestMessage(sseMessage)) {
          setPendingApproval(sseMessage);
          const toolName = sseMessage.tool_name || 'Unknown tool';
          addMessage('system', `🔐 Tool requires approval: ${toolName}`, 'approval_request', { tool_id: sseMessage.tool_id });
        }
      }
      
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        addMessage('system', '⚠️ Request cancelled', 'system');
      } else {
        addMessage('system', `❌ Error: ${error instanceof Error ? error.message : String(error)}`, 'error');
      }
    } finally {
      setIsResponding(false);
      abortControllerRef.current = null;
    }
  }, [isResponding, addMessage, handleSlashCommand, sessionId, showToolResults]);

  const handleToolDecision = useCallback(async (approved: boolean, feedback?: string) => {
    if (!pendingApproval || !isApprovalRequestMessage(pendingApproval)) return;

    try {
      const approvalMessage: ApprovalResponseMessage = {
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
    } catch (error) {
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
    handleToolDecision
  };
}