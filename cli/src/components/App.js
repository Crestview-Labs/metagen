import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */
import { useState, useEffect, useCallback } from 'react';
import { Box, Text, useInput, useApp, useStdin } from 'ink';
import { AuthenticationService, OpenAPI } from '../../../api/ts/src/index.js';
// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';
import { useTextBuffer } from './TextBuffer.js';
import { useMetagenStream } from '../hooks/useMetagenStream.js';
import { InputPrompt } from './InputPrompt.js';
import { ToolApprovalPrompt } from './ToolApprovalPrompt.js';
import { Spinner } from './Spinner.js';
// Default config
const defaultConfig = {
    getBackendUrl: () => process.env.METAGEN_BACKEND_URL || 'http://127.0.0.1:8080',
    getTimeout: () => parseInt(process.env.METAGEN_TIMEOUT || '30000'),
    getDebugMode: () => process.env.METAGEN_DEBUG === 'true'
};
// Simple validation function for file paths
const isValidPath = (path) => {
    return path.length > 0 && !path.includes('\0');
};
export const App = ({ initialMessage, autoApproveTools = false, exitOnComplete = false, minimalUI = false }) => {
    const { exit } = useApp();
    const { stdin, setRawMode } = useStdin();
    // Terminal size state
    const [terminalWidth, setTerminalWidth] = useState(process.stdout.columns || 80);
    const [terminalHeight, setTerminalHeight] = useState(process.stdout.rows || 24);
    // Use the streaming hook for chat functionality with auto-approval option
    const { messages, isResponding, sessionId, showToolResults, toggleToolResults, sendMessage, addMessage, handleSlashCommand, pendingApproval, handleToolDecision, toggleMessageExpanded } = useMetagenStream({
        autoApproveTools
    });
    // Authentication state
    const [authenticated, setAuthenticated] = useState(null);
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
    // Check authentication on startup and handle initial message
    useEffect(() => {
        const checkAuth = async () => {
            try {
                const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
                setAuthenticated(auth.authenticated);
                if (!auth.authenticated) {
                    addMessage('system', '⚠️  You are not authenticated. Type "/auth login" to authenticate with Google services.', 'error');
                }
                else if (!initialMessage) {
                    // Only show welcome message in interactive mode
                    addMessage('system', '🤖 Welcome to Metagen!\n\n💡 Tips:\n  • Type your message and press Enter\n  • Use "/" for commands (try "/help")\n  • Press Ctrl+C to exit\n  • Advanced text editing: Ctrl+A/E (home/end), Ctrl+W (delete word), Ctrl+arrows (word nav)', 'system');
                }
                // Send initial message if provided
                if (initialMessage) {
                    await sendMessage(initialMessage);
                }
            }
            catch (error) {
                setAuthenticated(false);
                addMessage('system', `❌ Error checking authentication: ${error instanceof Error ? error.message : error}`, 'error');
            }
        };
        checkAuth();
    }, [initialMessage, sendMessage, addMessage]);
    // Handle exit on complete for non-interactive mode
    useEffect(() => {
        if (exitOnComplete && !isResponding && messages.length > 0) {
            // Check if we have a final agent message
            const lastAgentMessage = messages.filter(m => m.type === 'agent').pop();
            if (lastAgentMessage && lastAgentMessage.metadata?.final) {
                // Exit after a short delay to ensure output is flushed
                setTimeout(() => exit(), 500);
            }
        }
    }, [exitOnComplete, isResponding, messages, exit]);
    // Handle quit commands that need to exit the app
    const handleQuitCommand = useCallback(async (command) => {
        const parts = command.slice(1).split(' ');
        const cmd = parts[0].toLowerCase();
        if (cmd === 'quit' || cmd === 'exit') {
            exit();
            return true;
        }
        return false;
    }, [exit]);
    // Create a submission handler
    const handleSubmit = useCallback((text) => {
        if (text.startsWith('/')) {
            handleQuitCommand(text).then(handled => {
                if (!handled) {
                    handleSlashCommand(text);
                }
            });
        }
        else {
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
            }
            else if (input === 'n' || input === 'N') {
                handleToolDecision(false);
            }
            else if (input === 'd' || input === 'D') {
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
    return (_jsxs(Box, { flexDirection: "column", width: "100%", minHeight: terminalHeight, children: [_jsxs(Box, { marginBottom: 1, children: [_jsx(Text, { bold: true, color: "blue", children: "\uD83E\uDD16 Metagen Interactive Chat" }), _jsx(Text, { children: " " }), sessionId && _jsxs(Text, { color: "gray", dimColor: true, children: ["Session: ", sessionId.slice(0, 8), "..."] }), _jsx(Text, { children: " " }), authenticated !== null && (_jsx(Text, { color: authenticated ? 'green' : 'red', children: authenticated ? '🟢' : '🔴' }))] }), _jsxs(Box, { flexDirection: "column", flexGrow: 1, paddingBottom: 1, children: [messages.map((message) => {
                        // Handle tool calls with collapsible details
                        if (message.type === 'tool_call' && message.metadata) {
                            return (_jsxs(Box, { marginBottom: 1, flexDirection: "column", children: [_jsxs(Text, { color: "cyan", children: ["\u2192 ", message.content, message.metadata.args && Object.keys(message.metadata.args).length > 0 && (_jsxs(Text, { dimColor: true, children: [" ", message.expanded ? '▼' : '▶'] }))] }), message.expanded && message.metadata.argsPreview && (_jsx(Box, { marginLeft: 2, children: _jsx(Text, { color: "gray", dimColor: true, children: message.metadata.argsPreview }) }))] }, message.id));
                        }
                        // Don't show tool results - they're handled by tool errors only
                        if (message.type === 'tool_result') {
                            return null;
                        }
                        // Show tool errors prominently
                        if (message.type === 'tool_error') {
                            return (_jsx(Box, { marginBottom: 1, children: _jsx(Text, { color: "red", bold: true, children: message.content }) }, message.id));
                        }
                        // Handle agent messages - streaming or final
                        if (message.type === 'agent') {
                            const isFinal = message.metadata?.final;
                            const content = message.content;
                            if (message.isStreaming) {
                                // Show streaming with a spinner/cursor
                                return (_jsx(Box, { marginBottom: 1, marginLeft: 2, children: _jsxs(Text, { color: "blue", children: [content, _jsx(Text, { color: "yellow", children: "\u258C" })] }) }, message.id));
                            }
                            else if (isFinal) {
                                // Only truly final responses in a box
                                return (_jsx(Box, { marginBottom: 1, borderStyle: "round", borderColor: "blue", padding: 1, children: _jsx(Text, { color: "blue", children: content }) }, message.id));
                            }
                            // Regular/intermediate agent message - no box
                            return (_jsx(Box, { marginBottom: 1, marginLeft: 2, children: _jsx(Text, { color: "blue", children: content }) }, message.id));
                        }
                        // Default rendering for other message types
                        return (_jsx(Box, { marginBottom: 1, children: message.type === 'user' ? (_jsxs(Text, { color: "green", bold: true, children: ["\uD83D\uDC64 ", message.content] })) : message.type === 'system' ? (_jsxs(Text, { color: "cyan", children: ["\uD83D\uDCA1 ", message.content] })) : message.type === 'error' ? (_jsxs(Text, { color: "red", children: ["\u274C ", message.content] })) : message.type === 'approval_request' ? (_jsxs(Text, { color: "yellow", bold: true, children: ["\uD83D\uDD10 ", message.content] })) : null }, message.id));
                    }), isResponding && !messages.some(m => m.isStreaming) && (_jsx(Box, { marginTop: 1, marginLeft: 2, children: _jsx(Spinner, { message: "Thinking" }) }))] }), pendingApproval && (_jsx(ToolApprovalPrompt, { approval: pendingApproval, onDecision: handleToolDecision, isResponding: isResponding })), _jsxs(Box, { flexDirection: "column", marginTop: 1, children: [_jsx(InputPrompt, { buffer: buffer, onSubmit: handleSubmit, inputWidth: inputWidth, focus: !isResponding && !pendingApproval }), _jsxs(Text, { color: "gray", dimColor: true, children: [pendingApproval ? 'Awaiting tool approval' : buffer.text.startsWith('/') ? 'Command mode' : 'Chat mode', " \u2022 Use \"/\" for commands \u2022 Press Ctrl+E to expand/collapse \u2022 Ctrl+C to exit"] })] })] }));
};
export default App;
