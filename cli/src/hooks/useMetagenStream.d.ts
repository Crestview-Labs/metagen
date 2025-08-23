/**
 * Hook for managing Metagen streaming chat interactions
 * Uses the generated OpenAPI TypeScript client
 */
export type UIMessageType = 'user' | 'agent' | 'system' | 'error' | 'thinking' | 'tool_call' | 'tool_started' | 'tool_result' | 'tool_error' | 'approval_request' | 'approval_response';
export interface StreamMessage {
    id: string;
    type: UIMessageType;
    content: string;
    timestamp: Date;
    metadata?: Record<string, any>;
    isStreaming?: boolean;
    expanded?: boolean;
}
export interface UseMetagenStreamReturn {
    messages: StreamMessage[];
    isResponding: boolean;
    sessionId: string;
    showToolResults: boolean;
    toggleToolResults: () => void;
    sendMessage: (message: string) => Promise<void>;
    addMessage: (sender: string, content: string, type?: UIMessageType, metadata?: Record<string, any>) => void;
    clearMessages: () => void;
    handleSlashCommand: (command: string) => Promise<void>;
    pendingApproval: any | null;
    handleToolDecision: (approved: boolean, feedback?: string) => Promise<void>;
    toggleMessageExpanded: (messageId: string) => void;
}
interface UseMetagenStreamOptions {
    autoApproveTools?: boolean;
}
export declare function useMetagenStream(options?: UseMetagenStreamOptions): UseMetagenStreamReturn;
export {};
