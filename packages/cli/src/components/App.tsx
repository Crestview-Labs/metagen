/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp, useStdin, Static } from 'ink';
import { apiClient } from '@metagen/api-client';
import { useTextBuffer } from './TextBuffer.js';
import { useMetagenStream } from '../hooks/useMetagenStream.js';
import { InputPrompt } from './InputPrompt.js';

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
  const { messages, isResponding, sessionId, showToolResults, toggleToolResults, sendMessage, addMessage, handleSlashCommand } = useMetagenStream();
  
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
        const isAuth = await apiClient.isAuthenticated();
        setAuthenticated(isAuth);
        
        if (!isAuth) {
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
        {messages.map((message) => (
          <Box key={message.id} marginBottom={1}>
            {message.type === 'user' ? (
              <Text color="green" bold>👤 You: {message.content}</Text>
            ) : message.type === 'agent' ? (
              <Box marginLeft={2}>
                <Text color="blue">{message.content}</Text>
              </Box>
            ) : message.type === 'tool_call' ? (
              <Text color="magenta" bold>  ├─ {message.content}</Text>
            ) : message.type === 'thinking' ? (
              <Text color="yellow" dimColor>  ├─ {message.content}</Text>
            ) : message.type === 'processing' ? (
              <Text color="yellow" dimColor>  ├─ {message.content}</Text>
            ) : message.type === 'tool_result' ? (
              <Text color="gray" dimColor>  ├─ {message.content}</Text>
            ) : message.type === 'system' ? (
              <Text color="cyan">💡 {message.content}</Text>
            ) : message.type === 'error' ? (
              <Text color="red">❌ {message.content}</Text>
            ) : null}
          </Box>
        ))}
      </Box>

      {/* Input area at bottom */}
      <Box flexDirection="column" marginTop={1}>
        <InputPrompt
          buffer={buffer}
          onSubmit={handleSubmit}
          inputWidth={inputWidth}
          focus={!isResponding}
        />
        <Text color="gray" dimColor>
          {buffer.text.startsWith('/') ? 'Command mode' : 'Chat mode'} • 
          Use "/" for commands • Tool results: {showToolResults ? 'ON' : 'OFF'} • Ctrl+C to exit
        </Text>
      </Box>
    </Box>
  );
};

export default App;