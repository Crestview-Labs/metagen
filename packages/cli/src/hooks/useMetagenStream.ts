/**
 * @license
 * Adapted from Google's Gemini CLI useGeminiStream
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useRef, useCallback } from 'react';
import { apiClient, ApprovalRequestMessage, ApprovalResponseMessage } from '@metagen/api-client';

export type MessageType = 'user' | 'agent' | 'system' | 'error' | 'chat' | 'thinking' | 'tool_call' | 'tool_started' | 'tool_result' | 'tool_error' | 'usage' | 'processing' | 'approval_request' | 'approval_response' | 'tool_approved' | 'tool_rejected';

export interface StreamMessage {
  id: string;
  type: MessageType;
  content: string;
  timestamp: Date;
  metadata?: Record<string, any>;
}

export interface UseMetagenStreamReturn {
  messages: StreamMessage[];
  isResponding: boolean;
  sessionId: string | null;
  showToolResults: boolean;
  toggleToolResults: () => void;
  sendMessage: (message: string) => Promise<void>;
  addMessage: (sender: string, content: string, type?: MessageType, metadata?: Record<string, any>) => void;
  clearMessages: () => void;
  handleSlashCommand: (command: string) => Promise<void>;
  pendingApproval: ApprovalRequestMessage | null;
  handleToolDecision: (approved: boolean, feedback?: string) => Promise<void>;
}

export function useMetagenStream(): UseMetagenStreamReturn {
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [isResponding, setIsResponding] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showToolResults, setShowToolResults] = useState(true);  // Default to true to show tool results
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequestMessage | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const addMessage = useCallback((sender: string, content: string, type: MessageType = 'agent', metadata?: Record<string, any>) => {
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
    setSessionId(null);
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
        addMessage('system', '📋 Available Commands:\n\n/help - Show this help\n/clear - Clear chat UI\n/clear-db - Clear database history\n/auth status - Check authentication\n/auth login - Login with Google\n/tools - List available tools\n/system health - Check system status\n/toggle-results - Toggle tool results display\n/quit or /exit - Exit chat', 'system');
        break;
        
      case 'toggle-results':
        toggleToolResults();
        addMessage('system', `🔍 Tool results display: ${!showToolResults ? 'OFF' : 'ON'}`, 'system');
        break;
        
      case 'clear':
        clearMessages();
        addMessage('system', '🧹 Chat UI cleared!', 'system');
        break;
        
      case 'clear-db':
        try {
          await apiClient.clearHistory();
          addMessage('system', '🗄️ Database history cleared! Agent will have fresh context.', 'system');
        } catch (error) {
          addMessage('system', `❌ Failed to clear database: ${error instanceof Error ? error.message : error}`, 'error');
        }
        break;
        
      case 'auth':
        if (args[0] === 'status') {
          try {
            const auth = await apiClient.getAuthStatus();
            if (auth.authenticated) {
              addMessage('system', `✅ Authenticated${auth.user_info?.email ? ` as ${auth.user_info.email}` : ''}`, 'system');
            } else {
              addMessage('system', '⚠️  Not authenticated. Use "/auth login" to authenticate.', 'error');
            }
          } catch (error) {
            addMessage('system', `❌ Auth check failed: ${error instanceof Error ? error.message : error}`, 'error');
          }
        } else if (args[0] === 'login') {
          try {
            const response = await apiClient.login();
            addMessage('system', `🔐 ${response.message}\n🌐 Open: ${response.auth_url}`, 'system');
          } catch (error) {
            addMessage('system', `❌ Login failed: ${error instanceof Error ? error.message : error}`, 'error');
          }
        }
        break;
        
      case 'tools':
        try {
          const tools = await apiClient.getTools();
          const toolsList = tools.tools.map((tool, i) => `  ${i + 1}. ${tool.name} - ${tool.description}`).join('\n');
          addMessage('system', `🔧 Available Tools (${tools.count}):\n\n${toolsList}`, 'system');
        } catch (error) {
          addMessage('system', `❌ Failed to fetch tools: ${error instanceof Error ? error.message : error}`, 'error');
        }
        break;
        
      case 'system':
        if (args[0] === 'health') {
          try {
            const health = await apiClient.getSystemHealth();
            const status = health.status.toUpperCase();
            const components = health.components ? Object.entries(health.components).map(([k, v]) => `  ${k}: ${v}`).join('\n') : '';
            addMessage('system', `🏥 System Health: ${status}\n\n${components}`, 'system');
          } catch (error) {
            addMessage('system', `❌ Health check failed: ${error instanceof Error ? error.message : error}`, 'error');
          }
        }
        break;

      case 'memory':
        if (args[0] === 'search') {
          const query = args.slice(1).join(' ');
          if (!query) {
            addMessage('system', '❓ Usage: /memory search <query>', 'error');
            return;
          }
          // TODO: Implement memory search when memory tools are re-enabled
          addMessage('system', '🚧 Memory search is temporarily disabled while we improve the system.', 'system');
        } else if (args[0] === 'recent') {
          // TODO: Implement recent conversations when memory tools are re-enabled
          addMessage('system', '🚧 Memory features are temporarily disabled while we improve the system.', 'system');
        } else {
          addMessage('system', '❓ Usage: /memory search <query> | /memory recent', 'error');
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
    
    // Don't add initial thinking - let the backend stream handle this

    try {
      // Use streaming API
      const streamGenerator = apiClient.sendMessageStream({ message: userMessage });
      
      let currentMessage = '';
      let messageId: string | null = null;
      let hasStartedResponse = false;
      
      for await (const streamResponse of streamGenerator) {
        // Check if aborted
        if (abortControllerRef.current?.signal.aborted) {
          break;
        }

        if (streamResponse.type === 'complete') {
          // Store session ID from completion
          if (streamResponse.session_id && !sessionId) {
            setSessionId(streamResponse.session_id);
          }
          break;
        }
        
        // Debug: Track responses to find missing large responses
        if (streamResponse.type === 'chat' && streamResponse.content?.length > 100) {
          console.log('📝 Large chat response:', streamResponse.content.length, 'chars');
        }
        
        // Handle different response types
        if (streamResponse.type === 'chat') {
          // Add response indicator when chat response starts
          if (!hasStartedResponse) {
            hasStartedResponse = true;
            // Add response indicator without clearing previous stages
            addMessage('system', '└─ response:', 'system');
          }
          
          // Accumulate text for smooth display
          currentMessage += streamResponse.content;
          
          if (!messageId) {
            // Create new message for first chunk
            messageId = `msg-${Date.now()}-${Math.random()}`;
            setMessages(prev => [...prev, {
              id: messageId!,
              type: 'agent',
              content: currentMessage,
              timestamp: new Date(),
              metadata: streamResponse.metadata
            }]);
          } else {
            // Update existing message
            setMessages(prev => prev.map(msg => 
              msg.id === messageId 
                ? { ...msg, content: currentMessage }
                : msg
            ));
          }
        } else if (streamResponse.type === 'thinking') {
          // Add thinking message (don't clear previous stages)
          addMessage('system', streamResponse.content, 'thinking', streamResponse.metadata);
        } else if (streamResponse.type === 'tool_call') {
          // Add tool call message (keep all previous stages)
          // Format tool calls for display
          let toolCallContent = streamResponse.content;
          if (streamResponse.metadata?.tool_calls || streamResponse.tool_calls) {
            const calls = streamResponse.metadata?.tool_calls || streamResponse.tool_calls;
            toolCallContent = `🔧 Calling ${calls.length} tool${calls.length > 1 ? 's' : ''}: ${calls.map((tc: any) => tc.tool_name).join(', ')}`;
          }
          addMessage('agent', toolCallContent, 'tool_call', streamResponse.metadata);
          
          // Reset message accumulation after tool calls so the next chat message creates a new message
          currentMessage = '';
          messageId = null;
          hasStartedResponse = false;
          
        } else if (streamResponse.type === 'tool_result') {
          // Show tool results if enabled
          if (showToolResults) {
            // ToolResultMessage has 'result' field, not 'content'
            const result = (streamResponse as any).result || '';
            const toolName = (streamResponse as any).tool_name || 'Unknown tool';
            const formattedResult = `📊 ${toolName} result:\n${typeof result === 'string' ? result : JSON.stringify(result, null, 2)}`;
            addMessage('system', formattedResult, 'tool_result', streamResponse.metadata);
          }
        } else if (streamResponse.type === 'tool_started') {
          // Add tool started message - ToolStartedMessage has tool_id and tool_name fields
          const toolName = (streamResponse as any).tool_name || 'Unknown tool';
          addMessage('system', `⚙️ Executing ${toolName}...`, 'processing', streamResponse.metadata);
        } else if (streamResponse.type === 'tool_error') {
          // Add tool error message - ToolErrorMessage has 'error' field, not 'content'
          const error = (streamResponse as any).error || 'Unknown error';
          const toolName = (streamResponse as any).tool_name || 'Unknown tool';
          addMessage('system', `❌ ${toolName} error: ${error}`, 'error', streamResponse.metadata);
        } else if (streamResponse.type === 'error') {
          // Handle ErrorMessage - this is a final error from the agent
          const errorContent = streamResponse.content || (streamResponse as any).error || 'Unknown error occurred';
          addMessage('system', `❌ Error: ${errorContent}`, 'error', streamResponse.metadata);
          // ErrorMessage is terminal - break the loop
          break;
        } else if (streamResponse.type === 'usage') {
          // Token usage information - could display or ignore
          // For now, we'll skip displaying usage info in the UI
        } else if ((streamResponse.type as string) === 'processing') {
          // Legacy processing message (keep for backward compatibility)
          addMessage('system', streamResponse.content, 'processing', streamResponse.metadata);
        } else if (streamResponse.type === 'approval_request') {
          // Extract approval request from metadata
          const approvalRequest = streamResponse.metadata?.approval_request as ApprovalRequestMessage;
          if (approvalRequest) {
            setPendingApproval(approvalRequest);
            addMessage('system', `🔐 Tool requires approval: ${streamResponse.content}`, 'approval_request', streamResponse.metadata);
          }
        } else if (streamResponse.type === 'approval_response') {
          // Handle approval response - check decision in metadata
          setPendingApproval(null);
          const decision = streamResponse.metadata?.decision;
          if (decision === 'approved') {
            addMessage('system', `✅ Tool approved: ${streamResponse.content}`, 'tool_approved', streamResponse.metadata);
          } else if (decision === 'rejected') {
            const feedback = streamResponse.metadata?.feedback;
            const message = feedback ? `${streamResponse.content} - Reason: ${feedback}` : streamResponse.content;
            addMessage('system', `❌ Tool rejected: ${message}`, 'tool_rejected', streamResponse.metadata);
          }
        } else {
          // Handle other message types
          const messageType = streamResponse.type as MessageType;
          addMessage('agent', streamResponse.content, messageType, streamResponse.metadata);
        }
      }
      
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        addMessage('system', '⚠️ Request cancelled', 'system');
      } else {
        addMessage('system', `❌ Error: ${error instanceof Error ? error.message : error}`, 'error');
      }
    } finally {
      setIsResponding(false);
      abortControllerRef.current = null;
    }
  }, [isResponding, addMessage, handleSlashCommand, sessionId, showToolResults]);

  const handleToolDecision = useCallback(async (approved: boolean, feedback?: string) => {
    if (!pendingApproval) return;

    try {
      const decision: ApprovalResponseMessage = {
        type: 'approval_response' as any,  // Type assertion needed due to enum mismatch
        direction: 'user_to_agent' as any,
        tool_id: pendingApproval.tool_id,
        decision: (approved ? 'approved' : 'rejected') as any,
        feedback: feedback,
        agent_id: pendingApproval.agent_id,
        timestamp: new Date().toISOString()
      } as ApprovalResponseMessage;

      await apiClient.sendToolDecision(decision);
      
      // Clear pending approval
      setPendingApproval(null);
    } catch (error) {
      addMessage('system', `❌ Failed to send tool decision: ${error instanceof Error ? error.message : error}`, 'error');
    }
  }, [pendingApproval, addMessage]);

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