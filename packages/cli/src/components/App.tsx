/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp, useStdin, Static } from 'ink';
import { AuthenticationService, OpenAPI } from '../../../../api/ts/src/index.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';
import { useTextBuffer } from './TextBuffer.js';
import { useMetagenStream } from '../hooks/useMetagenStream.js';
import { InputPrompt } from './InputPrompt.js';
import { ToolApprovalPrompt } from './ToolApprovalPrompt.js';
import { Spinner } from './Spinner.js';

// Simple config interface for our CLI
interface Config {
  getBackendUrl(): string;
  getTimeout(): number;
  getDebugMode(): boolean;
}

// Default config
const defaultConfig: Config = {
  getBackendUrl: () => process.env.METAGEN_BACKEND_URL || 'http://127.0.0.1:8080',
  getTimeout: () => parseInt(process.env.METAGEN_TIMEOUT || '30000'),
  getDebugMode: () => process.env.METAGEN_DEBUG === 'true'
};


// Simple validation function for file paths
const isValidPath = (path: string): boolean => {
  return path.length > 0 && !path.includes('\0');
};

export const App: React.FC = () => {
  const { exit } = useApp();
  const { stdin, setRawMode } = useStdin();
  
  // Terminal size state
  const [terminalWidth, setTerminalWidth] = useState(process.stdout.columns || 80);
  const [terminalHeight, setTerminalHeight] = useState(process.stdout.rows || 24);
  
  // Use the streaming hook for chat functionality
  const { messages, isResponding, sessionId, showToolResults, toggleToolResults, sendMessage, addMessage, handleSlashCommand, pendingApproval, handleToolDecision, toggleMessageExpanded } = useMetagenStream();
  
  // Authentication state
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  
  // Text input configuration
  const inputWidth = Math.max(20, Math.floor(terminalWidth * 0.9) - 3);
  const viewport = { height: 10, width: inputWidth };
  
  // Enable TextBuffer debug mode when debugging
  if (process.env.METAGEN_DEBUG) {
    process.env.TEXTBUFFER_DEBUG = '1';
  }
  
  // Text buffer for sophisticated input handling
  // Key prop forces recreation to prevent state corruption
  const buffer = useTextBuffer({
    initialText: '',
    viewport,
    stdin,
    setRawMode,
    isValidPath,
  });

  // Update terminal size on resize
  useEffect(() => {
    const updateSize = () => {
      setTerminalWidth(process.stdout.columns || 80);
      setTerminalHeight(process.stdout.rows || 24);
    };
    
    process.stdout.on('resize', updateSize);
    return () => {
      process.stdout.off('resize', updateSize);
    };
  }, []);

  // Check authentication on startup
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
        setAuthenticated(auth.authenticated);
        
        if (!auth.authenticated) {
          addMessage('system', '⚠️  You are not authenticated. Type "/auth login" to authenticate with Google services.', 'error');
        } else {
          addMessage('system', '🤖 Welcome to Metagen!\n\n💡 Tips:\n  • Type your message and press Enter\n  • Use "/" for commands (try "/help")\n  • Press Ctrl+C to exit\n  • Advanced text editing: Ctrl+A/E (home/end), Ctrl+W (delete word), Ctrl+arrows (word nav)', 'system');
        }
      } catch (error) {
        setAuthenticated(false);
        addMessage('system', `❌ Error checking authentication: ${error instanceof Error ? error.message : error}`, 'error');
      }
    };
    
    checkAuth();
  }, []);

  // Handle quit commands that need to exit the app
  const handleQuitCommand = useCallback(async (command: string) => {
    const parts = command.slice(1).split(' ');
    const cmd = parts[0].toLowerCase();
    
    if (cmd === 'quit' || cmd === 'exit') {
      exit();
      return true;
    }
    return false;
  }, [exit]);

  // Create a submission handler
  const handleSubmit = useCallback((text: string) => {
    if (text.startsWith('/')) {
      handleQuitCommand(text).then(handled => {
        if (!handled) {
          handleSlashCommand(text);
        }
      });
    } else {
      sendMessage(text);
    }
  }, [handleQuitCommand, handleSlashCommand, sendMessage]);

  // Handle global hotkeys only (let InputPrompt handle text input)
  useInput((input, key) => {
    if (key.ctrl && input === 'c') {
      exit();
      return;
    }
    
    // Handle expand/collapse for tool results  
    if (key.ctrl && input === 'e' && !pendingApproval) {
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
    
    // Handle tool approval keyboard shortcuts
    if (pendingApproval && !isResponding) {
      if (input === 'y' || input === 'Y') {
        handleToolDecision(true);
      } else if (input === 'n' || input === 'N') {
        handleToolDecision(false);
      } else if (input === 'd' || input === 'D') {
        // Show more details about the tool
        const details = pendingApproval.tool_args 
          ? JSON.stringify(pendingApproval.tool_args, null, 2)
          : 'No arguments';
        addMessage('system', 'Tool details: ' + details, 'system');
      }
    }
  });


  // Calculate layout following Gemini CLI pattern
  const headerHeight = 3;
  const inputHeight = 4; // Input + footer
  const availableHeight = terminalHeight - headerHeight - inputHeight;
  const mainAreaWidth = Math.floor(terminalWidth * 0.9);

  return (
    <Box flexDirection="column" width="100%" minHeight={terminalHeight}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="blue">🤖 Metagen Interactive Chat</Text>
        <Text> </Text>
        {sessionId && <Text color="gray" dimColor>Session: {sessionId.slice(0, 8)}...</Text>}
        <Text> </Text>
        {authenticated !== null && (
          <Text color={authenticated ? 'green' : 'red'}>
            {authenticated ? '🟢' : '🔴'}
          </Text>
        )}
      </Box>

      {/* Messages - Simple and stable */}
      <Box flexDirection="column" flexGrow={1} paddingBottom={1}>
        {messages.map((message) => {
          // Handle tool calls with collapsible details
          if (message.type === 'tool_call' && message.metadata) {
            return (
              <Box key={message.id} marginBottom={1} flexDirection="column">
                <Text color="cyan">
                  → {message.content}
                  {message.metadata.args && Object.keys(message.metadata.args).length > 0 && (
                    <Text dimColor> {message.expanded ? '▼' : '▶'}</Text>
                  )}
                </Text>
                {message.expanded && message.metadata.argsPreview && (
                  <Box marginLeft={2}>
                    <Text color="gray" dimColor>{message.metadata.argsPreview}</Text>
                  </Box>
                )}
              </Box>
            );
          }
          
          // Don't show tool results - they're handled by tool errors only
          if (message.type === 'tool_result') {
            return null;
          }
          
          // Show tool errors prominently
          if (message.type === 'tool_error') {
            return (
              <Box key={message.id} marginBottom={1}>
                <Text color="red" bold>{message.content}</Text>
              </Box>
            );
          }
          
          // Handle agent messages - streaming or final
          if (message.type === 'agent') {
            const isFinal = message.metadata?.final;
            const content = message.content;
            
            if (message.isStreaming) {
              // Show streaming with a spinner/cursor
              return (
                <Box key={message.id} marginBottom={1} marginLeft={2}>
                  <Text color="blue">
                    {content}
                    <Text color="yellow">▌</Text>
                  </Text>
                </Box>
              );
            } else if (isFinal) {
              // Only truly final responses in a box
              return (
                <Box key={message.id} marginBottom={1} borderStyle="round" borderColor="blue" padding={1}>
                  <Text color="blue">{content}</Text>
                </Box>
              );
            }
            
            // Regular/intermediate agent message - no box
            return (
              <Box key={message.id} marginBottom={1} marginLeft={2}>
                <Text color="blue">{content}</Text>
              </Box>
            );
          }
          
          // Default rendering for other message types
          return (
            <Box key={message.id} marginBottom={1}>
              {message.type === 'user' ? (
                <Text color="green" bold>👤 {message.content}</Text>
              ) : message.type === 'system' ? (
                <Text color="cyan">💡 {message.content}</Text>
              ) : message.type === 'error' ? (
                <Text color="red">❌ {message.content}</Text>
              ) : message.type === 'approval_request' ? (
                <Text color="yellow" bold>🔐 {message.content}</Text>
              ) : null}
            </Box>
          );
        })}
        
        {/* Show spinner when waiting for response but no streaming message yet */}
        {isResponding && !messages.some(m => m.isStreaming) && (
          <Box marginTop={1} marginLeft={2}>
            <Spinner message="Thinking" />
          </Box>
        )}
      </Box>

      {/* Tool approval prompt when needed */}
      {pendingApproval && (
        <ToolApprovalPrompt 
          approval={pendingApproval} 
          onDecision={handleToolDecision}
          isResponding={isResponding}
        />
      )}

      {/* Input area at bottom */}
      <Box flexDirection="column" marginTop={1}>
        <InputPrompt
          buffer={buffer}
          onSubmit={handleSubmit}
          inputWidth={inputWidth}
          focus={!isResponding && !pendingApproval}
        />
        <Text color="gray" dimColor>
          {pendingApproval ? 'Awaiting tool approval' : buffer.text.startsWith('/') ? 'Command mode' : 'Chat mode'} • 
          Use "/" for commands • Press Ctrl+E to expand/collapse • Ctrl+C to exit
        </Text>
      </Box>
    </Box>
  );
};

export default App;