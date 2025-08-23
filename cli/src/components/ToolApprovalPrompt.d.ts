import React from 'react';
interface ToolApprovalPromptProps {
    approval: any;
    onDecision: (approved: boolean, feedback?: string) => void;
    isResponding: boolean;
}
export declare const ToolApprovalPrompt: React.FC<ToolApprovalPromptProps>;
export {};
