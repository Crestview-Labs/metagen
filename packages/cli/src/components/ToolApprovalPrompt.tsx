import React, { useState } from 'react';
import { Box, Text } from 'ink';

interface ToolApprovalPromptProps {
  approval: any; // The raw SSE message from the server
  onDecision: (approved: boolean, feedback?: string) => void;
  isResponding: boolean;
}

export const ToolApprovalPrompt: React.FC<ToolApprovalPromptProps> = ({ 
  approval, 
  onDecision,
  isResponding 
}) => {
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
    } else {
      setShowingFeedback(true);
    }
  };

  return (
    <Box flexDirection="column" borderStyle="round" borderColor="yellow" padding={1} marginY={1}>
      <Text bold color="yellow">🔐 Tool Approval Required</Text>
      <Box marginTop={1}>
        <Text>Agent: </Text>
        <Text color="cyan">{approval.agent_id || 'METAGEN'}</Text>
      </Box>
      <Box>
        <Text>Tool: </Text>
        <Text color="magenta">{formatToolCall()}</Text>
      </Box>
      
      <Box marginTop={1}>
        <Text dimColor>Press Y to approve, N to reject, or type feedback and press Enter</Text>
      </Box>
      
      {showingFeedback && (
        <Box marginTop={1}>
          <Text color="red">Please provide feedback for rejection (or press Y to approve)</Text>
        </Box>
      )}
      
      {isResponding && (
        <Box marginTop={1}>
          <Text dimColor italic>Waiting for response...</Text>
        </Box>
      )}
    </Box>
  );
};