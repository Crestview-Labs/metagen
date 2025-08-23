import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp, Spacer, Static } from 'ink';
import { 
  AuthenticationService,
  OpenAPI
} from '../../../api/ts/src/index.js';
import { ToolApprovalPrompt } from './ToolApprovalPrompt.js';
import { useMetagenStream } from '../hooks/useMetagenStream.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

export const ChatInterface: React.FC = () => {
  const [input, setInput] = useState('');
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [staticKey, setStaticKey] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const [collectingFeedback, setCollectingFeedback] = useState(false);
  const [feedbackInput, setFeedbackInput] = useState('');
  const { exit } = useApp();

  // Use the streaming hook for all chat functionality
  const { 
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
  } = useMetagenStream();

  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
        setAuthenticated(auth.authenticated);
        
        if (!auth.authenticated) {
          addMessage('system', '⚠️  You are not authenticated. Type "/auth login" to authenticate with Google services.', 'error');
        } else {
          addMessage('system', '🤖 Welcome to Metagen interactive chat!\n\n💡 Tips:\n  • Type your message and press Enter\n  • Use "/help" for commands\n  • Press Ctrl+C to exit\n  • Type "/clear" to clear chat history\n  • Press Ctrl+E to expand/collapse tool results', 'system');
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

  const handleToolApprovalDecision = useCallback(async (approved: boolean, feedback?: string) => {
    await handleToolDecision(approved, feedback);
    setCollectingFeedback(false);
    setFeedbackInput('');
  }, [handleToolDecision]);

  const handleCommand = useCallback(async (command: string) => {
    const [cmd, ...args] = command.slice(1).split(' ');
    
    if (cmd.toLowerCase() === 'quit' || cmd.toLowerCase() === 'exit') {
      exit();
      return;
    }
    
    // Delegate all other commands to the hook
    await handleSlashCommand(command);
  }, [handleSlashCommand, exit]);

  const handleSendMessage = useCallback(async () => {
    if (!input.trim() || isResponding) return;
    
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

    // Send the message using the hook
    await sendMessage(userMessage);
  }, [input, isResponding, pendingApproval, addMessage, sendMessage, handleCommand]);

  // Track which message to expand/collapse
  const [expandIndex, setExpandIndex] = useState<number | null>(null);

  useInput((input: string, key: any) => {
    if (key.ctrl && input === 'c') {
      exit();
      return;
    }

    // Handle expand/collapse for tool results
    if (key.ctrl && input === 'e' && !collectingFeedback && !pendingApproval) {
      // Find the last tool result or tool call message
      let lastExpandable = -1;
      for (let i = messages.length - 1; i >= 0; i--) {
        const msg = messages[i];
        if ((msg.type === 'tool_result' || msg.type === 'tool_call') && msg.metadata) {
          lastExpandable = i;
          break;
        }
      }
      if (lastExpandable !== -1) {
        toggleMessageExpanded(messages[lastExpandable].id);
      }
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
    if (pendingApproval && !isResponding) {
      if (input?.toLowerCase() === 'y') {
        handleToolApprovalDecision(true);
        return;
      } else if (input?.toLowerCase() === 'n') {
        setCollectingFeedback(true);
        return;
      } else if (input?.toLowerCase() === 'd') {
        // Show details view
        const details = pendingApproval.tool_args 
          ? JSON.stringify(pendingApproval.tool_args, null, 2)
          : 'No arguments';
        addMessage('system', `Tool details: ${details}`, 'system');
        return;
      }
    }

    if (key.return) {
      handleSendMessage();
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
      case 'tool_started': return '▶️';
      case 'tool_result': return '📊';
      case 'tool_error': return '❌';
      case 'approval_request': return '🔐';
      case 'approval_response': return '🔐';
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
      case 'tool_started': return 'gray';
      case 'tool_result': return 'cyan';
      case 'tool_error': return 'red';
      case 'approval_request': return 'yellow';
      case 'approval_response': return 'yellow';
      default: return 'white';
    }
  };

  const renderMessage = (message: any) => {
    const icon = getMessageIcon(message.type);
    const color = getMessageColor(message.type);
    const timestamp = formatTimestamp(message.timestamp);
    
    // Handle tool calls with collapsible arguments
    if (message.type === 'tool_call' && message.metadata) {
      return (
        <Box flexDirection="column">
          <Text color={color}>
            {icon} [{timestamp}] {message.content}
            {message.metadata.args && (
              <Text dimColor> {message.expanded ? '▼' : '▶'} (Ctrl+E to {message.expanded ? 'collapse' : 'expand'})</Text>
            )}
          </Text>
          {message.expanded && message.metadata.argsPreview && (
            <Box marginLeft={4} marginTop={1}>
              <Text color="gray">{message.metadata.argsPreview}</Text>
            </Box>
          )}
        </Box>
      );
    }
    
    // Handle tool results with collapsible details
    if (message.type === 'tool_result' && message.metadata) {
      return (
        <Box flexDirection="column">
          <Text color={color}>
            {icon} [{timestamp}] {message.content}
            <Text dimColor> {message.expanded ? '▼' : '▶'} (press 'e' to {message.expanded ? 'collapse' : 'expand'})</Text>
          </Text>
          {message.expanded && message.metadata.result && (
            <Box marginLeft={4} marginTop={1}>
              <Text color="gray">{message.metadata.result.substring(0, 500)}{message.metadata.result.length > 500 ? '...' : ''}</Text>
            </Box>
          )}
        </Box>
      );
    }
    
    // Handle streaming agent messages
    if (message.type === 'agent' && message.isStreaming) {
      return (
        <Text color={color}>
          {icon} [{timestamp}] {message.content}
          <Text color="yellow">▌</Text>
        </Text>
      );
    }
    
    // Default message rendering
    return (
      <Text color={color}>
        {icon} [{timestamp}] {message.content}
      </Text>
    );
  };

  // Don't render until ready to avoid multiple redraws
  if (!isReady) {
    return <Text>Loading...</Text>;
  }

  return (
    <Box flexDirection="column">
      <Text bold color="blue">🤖 Metagen Chat {authenticated !== null && (authenticated ? '🟢' : '🔴')}</Text>
      <Text color="gray">Type your message, use /help for commands, Ctrl+C to exit</Text>
      
      {/* Messages - rendered in chronological order from the hook */}
      <Box flexDirection="column" marginTop={1}>
        {messages.map(message => (
          <Box key={message.id} marginBottom={1}>
            {renderMessage(message)}
          </Box>
        ))}
      </Box>
      
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
            isResponding={isResponding}
          />
        )
      ) : (
        <Box marginTop={1}>
          <Text>{'>'} {input}</Text>
          {isResponding && <Text color="yellow"> [Processing your request...]</Text>}
        </Box>
      )}
    </Box>
  );
};