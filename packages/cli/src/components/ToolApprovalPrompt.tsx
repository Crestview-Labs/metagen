import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { ToolApprovalRequest } from '@metagen/api-client';

interface ToolApprovalPromptProps {
  approval: ToolApprovalRequest;
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

  const formatToolCall = () => {
    const args = Object.entries(approval.tool_args)
      .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
      .join(', ');
    return `${approval.tool_name}(${args})`;
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
        <Text color="cyan">{approval.agent_id}</Text>
      </Box>
      <Box>
        <Text>Tool: </Text>
        <Text color="magenta">{formatToolCall()}</Text>
      </Box>
      {approval.description && (
        <Box>
          <Text>Description: </Text>
          <Text color="gray">{approval.description}</Text>
        </Box>
      )}
      {approval.risk_level && (
        <Box>
          <Text>Risk Level: </Text>
          <Text color={approval.risk_level === 'high' ? 'red' : approval.risk_level === 'medium' ? 'yellow' : 'green'}>
            {approval.risk_level.toUpperCase()}
          </Text>
        </Box>
      )}
      
      <Box marginTop={1} flexDirection="column">
        {!showingFeedback ? (
          <Box>
            <Text bold>[Y]es, approve  [N]o, reject  [D]etails</Text>
            {isResponding && <Text color="gray"> (waiting for agent...)</Text>}
          </Box>
        ) : (
          <Box flexDirection="column">
            <Text>Rejection reason (optional, press Enter to skip):</Text>
            <Box>
              <Text>{'> '}{feedback}</Text>
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
};