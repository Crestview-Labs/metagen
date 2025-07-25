import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp, Spacer, Static } from 'ink';
import { apiClient, ChatResponse, StreamResponse } from '@metagen/api-client';

interface Message {
  id: string;
  type: 'user' | 'agent' | 'error' | 'system' | 'thinking' | 'tool_call' | 'tool_result';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  metadata?: Record<string, any>;
}

export const ChatInterface: React.FC = () => {
  const [staticMessages, setStaticMessages] = useState<Message[]>([]);
  const [pendingMessages, setPendingMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [staticKey, setStaticKey] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const { exit } = useApp();

  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const isAuth = await apiClient.isAuthenticated();
        setAuthenticated(isAuth);
        
        if (!isAuth) {
          addMessage('system', '⚠️  You are not authenticated. Type "/auth login" to authenticate with Google services.', 'error');
        } else {
          addMessage('system', '🤖 Welcome to Metagen interactive chat!\n\n💡 Tips:\n  • Type your message and press Enter\n  • Use "/help" for commands\n  • Press Ctrl+C to exit\n  • Type "/clear" to clear chat history', 'system');
        }
      } catch (error) {
        setAuthenticated(false);
        addMessage('system', `❌ Error checking authentication: ${error instanceof Error ? error.message : error}`, 'error');
      }
    };
    
    checkAuth();
    
    // Delay rendering to avoid multiple redraws
    setTimeout(() => setIsReady(true), 100);
  }, []);

  const addMessage = useCallback((sender: string, content: string, type: 'user' | 'agent' | 'error' | 'system' | 'thinking' | 'tool_call' | 'tool_result' = 'agent', metadata?: Record<string, any>) => {
    const message: Message = {
      id: `${Date.now()}-${Math.random()}`,
      type,
      content,
      timestamp: new Date(),
      metadata
    };
    setPendingMessages(prev => [...prev, message]);
  }, []);

  const handleCommand = useCallback(async (command: string) => {
    const [cmd, ...args] = command.slice(1).split(' ');
    
    switch (cmd.toLowerCase()) {
      case 'help':
        addMessage('system', '📋 Available Commands:\n\n/help - Show this help\n/clear - Clear chat history\n/auth status - Check authentication\n/auth login - Login with Google\n/tools - List available tools\n/system health - Check system status\n/quit or /exit - Exit chat', 'system');
        break;
        
      case 'clear':
        setStaticMessages([]);
        setPendingMessages([]);
        setStaticKey(prev => prev + 1);
        addMessage('system', '🧹 Chat history cleared!', 'system');
        break;
        
      case 'quit':
      case 'exit':
        exit();
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
        
      default:
        addMessage('system', `❓ Unknown command: /${cmd}. Type "/help" for available commands.`, 'error');
    }
  }, [addMessage, exit]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');

    // Handle commands
    if (userMessage.startsWith('/')) {
      await handleCommand(userMessage);
      return;
    }

    setIsLoading(true);

    // Add user message
    addMessage('user', userMessage, 'user');

    try {
      // Use streaming API
      const streamGenerator = apiClient.sendMessageStream({ message: userMessage });
      
      for await (const streamResponse of streamGenerator) {
        if (streamResponse.type === 'complete') {
          // Store session ID from completion
          if (streamResponse.session_id && !sessionId) {
            setSessionId(streamResponse.session_id);
          }
          break;
        }
        
        // Handle different response types
        const messageType = streamResponse.type === 'text' ? 'agent' : streamResponse.type as Message['type'];
        
        addMessage('agent', streamResponse.content, messageType, streamResponse.metadata);
      }
      
    } catch (error) {
      addMessage('system', `❌ Error: ${error instanceof Error ? error.message : error}`, 'error');
    } finally {
      setIsLoading(false);
      // Move pending messages to static after completion
      setTimeout(() => {
        setPendingMessages(pending => {
          if (pending.length > 0) {
            setStaticMessages(staticMsgs => [...staticMsgs, ...pending]);
            setStaticKey(prev => prev + 1);
            return [];
          }
          return pending;
        });
      }, 100);
    }
  }, [input, isLoading, addMessage, handleCommand, sessionId]);

  useInput((input: string, key: any) => {
    if (key.ctrl && input === 'c') {
      exit();
      return;
    }

    if (key.return) {
      sendMessage();
      return;
    }

    if (key.backspace || key.delete) {
      setInput(prev => prev.slice(0, -1));
      return;
    }

    if (input && !key.ctrl && !key.meta) {
      setInput(prev => prev + input);
    }
  });

  const formatTimestamp = (date: Date) => {
    return date.toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    });
  };

  const getMessageIcon = (type: string) => {
    switch (type) {
      case 'user': return '👤';
      case 'agent': return '🤖';
      case 'error': return '❌';
      case 'system': return '💡';
      case 'thinking': return '🤔';
      case 'tool_call': return '🔧';
      case 'tool_result': return '📊';
      default: return '📝';
    }
  };

  const getMessageColor = (type: string) => {
    switch (type) {
      case 'user': return 'green';
      case 'agent': return 'blue';
      case 'error': return 'red';
      case 'system': return 'cyan';
      case 'thinking': return 'yellow';
      case 'tool_call': return 'magenta';
      case 'tool_result': return 'cyan';
      default: return 'white';
    }
  };

  // Don't render until ready to avoid multiple redraws
  if (!isReady) {
    return <Text>Loading...</Text>;
  }

  return (
    <Box flexDirection="column">
      <Text bold color="blue">🤖 Metagen Chat {authenticated !== null && (authenticated ? '🟢' : '🔴')}</Text>
      <Text color="gray">Type your message, use /help for commands, Ctrl+C to exit</Text>
      
      {/* Static messages - rendered once and never re-rendered */}
      <Static key={staticKey} items={staticMessages.map(message => (
        <Box key={message.id} marginBottom={1}>
          <Text color={getMessageColor(message.type)}>
            {getMessageIcon(message.type)} [{formatTimestamp(message.timestamp)}] {message.content}
          </Text>
        </Box>
      ))}>
        {(item) => item}
      </Static>
      
      {/* Pending messages - dynamically rendered */}
      {pendingMessages.map(message => (
        <Box key={message.id} marginBottom={1}>
          <Text color={getMessageColor(message.type)}>
            {getMessageIcon(message.type)} [{formatTimestamp(message.timestamp)}] {message.content}
          </Text>
        </Box>
      ))}
      
      {/* Input area */}
      <Box marginTop={1}>
        <Text>{'>'} {input}</Text>
        {isLoading && <Text color="yellow"> [Thinking...]</Text>}
      </Box>
    </Box>
  );
};