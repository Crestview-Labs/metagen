import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { Box, Text } from 'ink';
export const ToolApprovalPrompt = ({ approval, onDecision, isResponding }) => {
    const [feedback, setFeedback] = useState('');
    const [showingFeedback, setShowingFeedback] = useState(false);
    if (!approval.tool_name) {
        return null;
    }
    const formatToolCall = () => {
        if (approval.tool_args && Object.keys(approval.tool_args).length > 0) {
            const args = Object.entries(approval.tool_args)
                .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
                .join(', ');
            return `${approval.tool_name}(${args})`;
        }
        return approval.tool_name;
    };
    const handleApprove = () => {
        onDecision(true);
    };
    const handleReject = () => {
        if (feedback.trim()) {
            onDecision(false, feedback.trim());
        }
        else {
            setShowingFeedback(true);
        }
    };
    return (_jsxs(Box, { flexDirection: "column", borderStyle: "round", borderColor: "yellow", padding: 1, marginY: 1, children: [_jsx(Text, { bold: true, color: "yellow", children: "\uD83D\uDD10 Tool Approval Required" }), _jsxs(Box, { marginTop: 1, children: [_jsx(Text, { children: "Agent: " }), _jsx(Text, { color: "cyan", children: approval.agent_id || 'METAGEN' })] }), _jsxs(Box, { children: [_jsx(Text, { children: "Tool: " }), _jsx(Text, { color: "magenta", children: formatToolCall() })] }), _jsx(Box, { marginTop: 1, children: _jsx(Text, { dimColor: true, children: "Press Y to approve, N to reject, or type feedback and press Enter" }) }), showingFeedback && (_jsx(Box, { marginTop: 1, children: _jsx(Text, { color: "red", children: "Please provide feedback for rejection (or press Y to approve)" }) })), isResponding && (_jsx(Box, { marginTop: 1, children: _jsx(Text, { dimColor: true, italic: true, children: "Waiting for response..." }) }))] }));
};
