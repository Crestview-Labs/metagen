import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import { useState, useEffect, useCallback } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import { AuthenticationService, OpenAPI } from '../../../api/ts/src/index.js';
import { ToolApprovalPrompt } from './ToolApprovalPrompt.js';
import { useMetagenStream } from '../hooks/useMetagenStream.js';
// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';
export const ChatInterface = () => {
    const [input, setInput] = useState('');
    const [authenticated, setAuthenticated] = useState(null);
    const [staticKey, setStaticKey] = useState(0);
    const [isReady, setIsReady] = useState(false);
    const [collectingFeedback, setCollectingFeedback] = useState(false);
    const [feedbackInput, setFeedbackInput] = useState('');
    const { exit } = useApp();
    // Use the streaming hook for all chat functionality
    const { messages, isResponding, sessionId, showToolResults, toggleToolResults, sendMessage, addMessage, clearMessages, handleSlashCommand, pendingApproval, handleToolDecision, toggleMessageExpanded } = useMetagenStream();
    // Check authentication on mount
    useEffect(() => {
        const checkAuth = async () => {
            try {
                const auth = await AuthenticationService.getAuthStatusApiAuthStatusGet();
                setAuthenticated(auth.authenticated);
                if (!auth.authenticated) {
                    addMessage('system', '⚠️  You are not authenticated. Type "/auth login" to authenticate with Google services.', 'error');
                }
                else {
                    addMessage('system', '🤖 Welcome to Metagen interactive chat!\n\n💡 Tips:\n  • Type your message and press Enter\n  • Use "/help" for commands\n  • Press Ctrl+C to exit\n  • Type "/clear" to clear chat history\n  • Press Ctrl+E to expand/collapse tool results', 'system');
                }
            }
            catch (error) {
                setAuthenticated(false);
                addMessage('system', `❌ Error checking authentication: ${error instanceof Error ? error.message : error}`, 'error');
            }
        };
        checkAuth();
        // Delay rendering to avoid multiple redraws
        setTimeout(() => setIsReady(true), 100);
    }, []);
    const handleToolApprovalDecision = useCallback(async (approved, feedback) => {
        await handleToolDecision(approved, feedback);
        setCollectingFeedback(false);
        setFeedbackInput('');
    }, [handleToolDecision]);
    const handleCommand = useCallback(async (command) => {
        const [cmd, ...args] = command.slice(1).split(' ');
        if (cmd.toLowerCase() === 'quit' || cmd.toLowerCase() === 'exit') {
            exit();
            return;
        }
        // Delegate all other commands to the hook
        await handleSlashCommand(command);
    }, [handleSlashCommand, exit]);
    const handleSendMessage = useCallback(async () => {
        if (!input.trim() || isResponding)
            return;
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
    const [expandIndex, setExpandIndex] = useState(null);
    useInput((input, key) => {
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
            }
            else if (input?.toLowerCase() === 'n') {
                setCollectingFeedback(true);
                return;
            }
            else if (input?.toLowerCase() === 'd') {
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
    const formatTimestamp = (date) => {
        return date.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    };
    const getMessageIcon = (type) => {
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
    const getMessageColor = (type) => {
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
    const renderMessage = (message) => {
        const icon = getMessageIcon(message.type);
        const color = getMessageColor(message.type);
        const timestamp = formatTimestamp(message.timestamp);
        // Handle tool calls with collapsible arguments
        if (message.type === 'tool_call' && message.metadata) {
            return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Text, { color: color, children: [icon, " [", timestamp, "] ", message.content, message.metadata.args && (_jsxs(Text, { dimColor: true, children: [" ", message.expanded ? '▼' : '▶', " (Ctrl+E to ", message.expanded ? 'collapse' : 'expand', ")"] }))] }), message.expanded && message.metadata.argsPreview && (_jsx(Box, { marginLeft: 4, marginTop: 1, children: _jsx(Text, { color: "gray", children: message.metadata.argsPreview }) }))] }));
        }
        // Handle tool results with collapsible details
        if (message.type === 'tool_result' && message.metadata) {
            return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Text, { color: color, children: [icon, " [", timestamp, "] ", message.content, _jsxs(Text, { dimColor: true, children: [" ", message.expanded ? '▼' : '▶', " (press 'e' to ", message.expanded ? 'collapse' : 'expand', ")"] })] }), message.expanded && message.metadata.result && (_jsx(Box, { marginLeft: 4, marginTop: 1, children: _jsxs(Text, { color: "gray", children: [message.metadata.result.substring(0, 500), message.metadata.result.length > 500 ? '...' : ''] }) }))] }));
        }
        // Handle streaming agent messages
        if (message.type === 'agent' && message.isStreaming) {
            return (_jsxs(Text, { color: color, children: [icon, " [", timestamp, "] ", message.content, _jsx(Text, { color: "yellow", children: "\u258C" })] }));
        }
        // Default message rendering
        return (_jsxs(Text, { color: color, children: [icon, " [", timestamp, "] ", message.content] }));
    };
    // Don't render until ready to avoid multiple redraws
    if (!isReady) {
        return _jsx(Text, { children: "Loading..." });
    }
    return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Text, { bold: true, color: "blue", children: ["\uD83E\uDD16 Metagen Chat ", authenticated !== null && (authenticated ? '🟢' : '🔴')] }), _jsx(Text, { color: "gray", children: "Type your message, use /help for commands, Ctrl+C to exit" }), _jsx(Box, { flexDirection: "column", marginTop: 1, children: messages.map(message => (_jsx(Box, { marginBottom: 1, children: renderMessage(message) }, message.id))) }), pendingApproval ? (collectingFeedback ? (_jsx(Box, { marginTop: 1, borderStyle: "round", borderColor: "yellow", padding: 1, children: _jsxs(Box, { flexDirection: "column", children: [_jsx(Text, { color: "yellow", children: "Rejection reason (optional, press Enter to skip):" }), _jsx(Box, { marginTop: 1, children: _jsxs(Text, { children: ['> ', feedbackInput] }) })] }) })) : (_jsx(ToolApprovalPrompt, { approval: pendingApproval, onDecision: handleToolApprovalDecision, isResponding: isResponding }))) : (_jsxs(Box, { marginTop: 1, children: [_jsxs(Text, { children: ['>', " ", input] }), isResponding && _jsx(Text, { color: "yellow", children: " [Processing your request...]" })] }))] }));
};
