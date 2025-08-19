import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp, Spacer, Static } from 'ink';
import { 
  AuthenticationService,
  ChatService,
  ToolsService,
  SystemService,
  MemoryService,
  MetagenStreamingClient,
  OpenAPI,
  type SSEMessage,
  ApprovalDecision,
  MessageType,
  type ApprovalResponseMessage
} from '../../../../api/ts/src/index.js';
import { ToolApprovalPrompt } from './ToolApprovalPrompt.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

interface Message {
  id: string;
  type: 'user' | 'agent' | 'error' | 'system' | 'thinking' | 'tool_call' | 'tool_result' | 'approval_request' | 'tool_approved' | 'tool_rejected';
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
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);
  const [isWaitingForApproval, setIsWaitingForApproval] = useState(false);
  const [collectingFeedback, setCollectingFeedback] = useState(false);
  const [feedbackInput, setFeedbackInput] = useState('');
  const { exit } = useApp();

  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
        setAuthenticated(auth.authenticated);
        
        if (!auth.authenticated) {
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

  const addMessage = useCallback((sender: string, content: string, type: 'user' | 'agent' | 'error' | 'system' | 'thinking' | 'tool_call' | 'tool_result' | 'approval_request' | 'tool_approved' | 'tool_rejected' = 'agent', metadata?: Record<string, any>) => {
    const message: Message = {
      id: `${Date.now()}-${Math.random()}`,
      type,
      content,
      timestamp: new Date(),
      metadata
    };
    setPendingMessages(prev => [...prev, message]);
  }, []);

  const handleToolApprovalDecision = useCallback(async (approved: boolean, feedback?: string) => {
    if (!pendingApproval) return;
    
    setIsWaitingForApproval(true);
    
    try {
      // Send the approval decision to the API
      const approvalMessage: ApprovalResponseMessage = {
        type: MessageType.APPROVAL_RESPONSE,
        timestamp: new Date().toISOString(),
        agent_id: (pendingApproval as any).agent_id || 'USER',
        session_id: sessionId || '',
        tool_id: (pendingApproval as any).tool_id,
        decision: approved ? ApprovalDecision.APPROVED : ApprovalDecision.REJECTED,
        feedback: feedback
      };
      
      await ChatService.handleApprovalResponseApiChatApprovalResponsePost({
        requestBody: approvalMessage
      });
      
      // Clear the pending approval and feedback state
      setPendingApproval(null);
      setCollectingFeedback(false);
      setFeedbackInput('');
      
      // Add a message to show the decision
      const statusMsg = approved 
        ? `🔐 Tool approved: ${pendingApproval.tool_name}`
        : `🔐 Tool rejected: ${pendingApproval.tool_name}${feedback ? ` (${feedback})` : ''}`;
      addMessage('system', statusMsg, approved ? 'tool_approved' : 'tool_rejected');
    } catch (error) {
      addMessage('system', `❌ Error sending tool decision: ${error instanceof Error ? error.message : error}`, 'error');
    } finally {
      setIsWaitingForApproval(false);
    }
  }, [pendingApproval, addMessage]);

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
            const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
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
            const response = await AuthenticationService.loginApiAuthLoginPost({
              requestBody: { force: false }
            });
            addMessage('system', `🔐 ${response.message}\n🌐 Open: ${response.auth_url}`, 'system');
          } catch (error) {
            addMessage('system', `❌ Login failed: ${error instanceof Error ? error.message : error}`, 'error');
          }
        }
        break;
        
      case 'tools':
        try {
          const tools = await ToolsService.getToolsApiToolsGet();
          const toolsList = tools.tools.map((tool, i) => `  ${i + 1}. ${tool.name} - ${tool.description}`).join('\n');
          addMessage('system', `🔧 Available Tools (${tools.count}):\n\n${toolsList}`, 'system');
        } catch (error) {
          addMessage('system', `❌ Failed to fetch tools: ${error instanceof Error ? error.message : error}`, 'error');
        }
        break;
        
      case 'system':
        if (args[0] === 'health') {
          try {
            await SystemService.healthCheckApiSystemHealthGet();
            addMessage('system', `🏥 System Health: HEALTHY`, 'system');
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
    
    // Don't allow sending messages while there's a pending approval
    if (pendingApproval) {
      addMessage('system', '⚠️  Please respond to the tool approval request first (Y/N/D)', 'system');
      return;
    }

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
      const client = new MetagenStreamingClient();
      // Generate a session ID if we don't have one
      if (!sessionId) {
        const newSessionId = Math.random().toString(36).substring(2) + Date.now().toString(36);
        setSessionId(newSessionId);
      }
      
      const streamGenerator = client.chatStream({ message: userMessage, session_id: sessionId || '' });
      
      for await (const message of streamGenerator) {
        // Check for completion (AgentMessage with final flag)
        if (message.type === MessageType.AGENT && (message as any).final) {
          break;
        }
        
        // Handle different response types
        switch (message.type) {
          case MessageType.AGENT:
            addMessage('agent', (message as any).content, 'agent', (message as any).metadata);
            break;
          case MessageType.THINKING:
            addMessage('system', (message as any).content, 'thinking', (message as any).metadata);
            break;
          case MessageType.TOOL_CALL:
            addMessage('system', `🔧 Calling tool: ${(message as any).tool_name}`, 'tool_call', { tool_id: (message as any).tool_id });
            break;
          case MessageType.TOOL_RESULT:
            addMessage('system', `✅ Result from ${(message as any).tool_name}`, 'tool_result', { tool_id: (message as any).tool_id });
            break;
          case MessageType.TOOL_ERROR:
            addMessage('system', `❌ Tool error: ${(message as any).error}`, 'error', { tool_id: (message as any).tool_id });
            break;
          case MessageType.APPROVAL_REQUEST:
            setPendingApproval(message);
            addMessage('system', `🔐 Tool requires approval: ${(message as any).tool_name}`, 'approval_request', { tool_id: (message as any).tool_id });
            break;
          case MessageType.ERROR:
            addMessage('system', `❌ ${(message as any).message}`, 'error', {});
            break;
        }
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

    // Handle feedback collection
    if (collectingFeedback) {
      if (key.return) {
        // Submit rejection with feedback
        handleToolApprovalDecision(false, feedbackInput.trim() || undefined);
        setCollectingFeedback(false);
        setFeedbackInput('');
        return;
      }
      
      if (key.backspace || key.delete) {
        setFeedbackInput(prev => prev.slice(0, -1));
        return;
      }
      
      if (input && !key.ctrl && !key.meta) {
        setFeedbackInput(prev => prev + input);
      }
      return;
    }

    // Handle tool approval shortcuts
    if (pendingApproval && !isWaitingForApproval) {
      if (input?.toLowerCase() === 'y') {
        handleToolApprovalDecision(true);
        return;
      } else if (input?.toLowerCase() === 'n') {
        setCollectingFeedback(true);
        return;
      } else if (input?.toLowerCase() === 'd') {
        // TODO: Show details view
        addMessage('system', 'Details view not yet implemented', 'system');
        return;
      }
    }

    if (key.return) {
      sendMessage();
      return;
    }

    if (key.backspace || key.delete) {
      setInput(prev => prev.slice(0, -1));
      return;
    }

    if (input && !key.ctrl && !key.meta && !pendingApproval) {
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
      case 'approval_request': return '🔐';
      case 'tool_approved': return '✅';
      case 'tool_rejected': return '❌';
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
      case 'approval_request': return 'yellow';
      case 'tool_approved': return 'green';
      case 'tool_rejected': return 'red';
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
      
      {/* Input area or Tool Approval Prompt */}
      {pendingApproval ? (
        collectingFeedback ? (
          <Box marginTop={1} borderStyle="round" borderColor="yellow" padding={1}>
            <Box flexDirection="column">
              <Text color="yellow">Rejection reason (optional, press Enter to skip):</Text>
              <Box marginTop={1}>
                <Text>{'> '}{feedbackInput}</Text>
              </Box>
            </Box>
          </Box>
        ) : (
          <ToolApprovalPrompt
            approval={pendingApproval}
            onDecision={handleToolApprovalDecision}
            isResponding={isWaitingForApproval}
          />
        )
      ) : (
        <Box marginTop={1}>
          <Text>{'>'} {input}</Text>
          {isLoading && <Text color="yellow"> [Thinking...]</Text>}
        </Box>
      )}
    </Box>
  );
};