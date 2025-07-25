/**
 * @license
 * Adapted from Google's Gemini CLI useGeminiStream
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useRef, useCallback } from 'react';
import { apiClient } from '@metagen/api-client';

export type MessageType = 'user' | 'agent' | 'system' | 'error' | 'thinking' | 'tool_call' | 'tool_result' | 'processing';

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
}

export function useMetagenStream(): UseMetagenStreamReturn {
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [isResponding, setIsResponding] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showToolResults, setShowToolResults] = useState(false);
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
        addMessage('system', `🔍 Tool results display: ${showToolResults ? 'OFF' : 'ON'}`, 'system');
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
              addMessage('system', `✅ Authenticated${auth.email ? ` as ${auth.email}` : ''}`, 'system');
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
        
        // Debug: Track responses to find missing 872-char email summary
        if (streamResponse.type === 'text' && streamResponse.content?.length > 100) {
          console.log('📝 Large text response:', streamResponse.content.length, 'chars');
        }
        
        // Handle different response types
        if (streamResponse.type === 'text') {
          // Add response indicator when text response starts
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
          addMessage('agent', streamResponse.content, 'tool_call', streamResponse.metadata);
          
        } else if (streamResponse.type === 'tool_result') {
          // Show tool results if enabled
          if (showToolResults) {
            const result = streamResponse.content;
            addMessage('system', result, 'tool_result', streamResponse.metadata);
          }
        } else if ((streamResponse.type as string) === 'processing') {
          // Add processing message (keep all previous stages)
          addMessage('system', streamResponse.content, 'processing', streamResponse.metadata);
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

  return {
    messages,
    isResponding,
    sessionId,
    showToolResults,
    toggleToolResults,
    sendMessage,
    addMessage,
    clearMessages,
    handleSlashCommand
  };
}