// Auto-generated TypeScript types from Metagen Python API
// Generated according to docs/api-stub-generation-design.md
// Last updated: 2025-01-07

// ============================================================================
// ENUMS - Direct mapping from Python enums
// ============================================================================

export enum MessageType {
  // Chat/content
  CHAT = "chat",
  THINKING = "thinking",
  
  // Tool flow
  TOOL_CALL = "tool_call",
  APPROVAL_REQUEST = "approval_request",
  APPROVAL_RESPONSE = "approval_response",
  TOOL_STARTED = "tool_started",
  TOOL_RESULT = "tool_result",
  TOOL_ERROR = "tool_error",
  
  // Metadata
  USAGE = "usage",
  ERROR = "error",
}

export enum Direction {
  USER_TO_AGENT = "user_to_agent",
  AGENT_TO_USER = "agent_to_user",
}

export enum ApprovalDecision {
  APPROVED = "approved",
  REJECTED = "rejected",
}

// ============================================================================
// MODELS FROM api/models/chat.py
// ============================================================================

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface UIResponseModel {
  type: string;
  content: string;
  agent_id: string;
  metadata?: Record<string, any>;
  timestamp: string;
}

export interface ChatResponse {
  responses: UIResponseModel[];
  session_id?: string;
  success: boolean;
}

// ============================================================================
// MODELS FROM api/models/auth.py
// ============================================================================

export interface AuthStatus {
  authenticated: boolean;
  user_info?: Record<string, string>;
  services: string[];
  provider?: string;
}

export interface AuthLoginRequest {
  force?: boolean;
}

export interface AuthResponse {
  success: boolean;
  message: string;
  auth_url?: string;
  status?: AuthStatus;
}

// Legacy alias for backward compatibility - the login endpoint returns AuthResponse
export interface AuthLoginResponse extends AuthResponse {}

// ============================================================================
// MODELS FROM api/models/system.py
// ============================================================================

export interface ToolInfo {
  name: string;
  description: string;
  input_schema: Record<string, any>;
}

export interface ToolsResponse {
  tools: ToolInfo[];
  count: number;
}

export interface SystemInfo {
  agent_name: string;
  model: string;
  tools: ToolInfo[];
  tool_count: number;
  memory_path: string;
  initialized: boolean;
}

// ============================================================================
// MODELS FROM api/models/common.py
// ============================================================================

export interface ErrorResponse {
  error: string;
  error_type?: string;
  timestamp: string;
}

export interface SuccessResponse {
  message: string;
  data?: Record<string, any>;
  timestamp: string;
}

// ============================================================================
// MODELS FROM common/messages.py
// ============================================================================

export interface Message {
  type: MessageType;
  direction: Direction;
  timestamp: string;
  agent_id: string;
}

export interface ToolCallRequest {
  tool_id: string;
  tool_name: string;
  tool_args: Record<string, any>;
}

export interface ChatMessage extends Message {
  type: MessageType.CHAT;
  content: string;
}

export interface UserMessage extends ChatMessage {
  direction: Direction.USER_TO_AGENT;
}

export interface AgentMessage extends ChatMessage {
  direction: Direction.AGENT_TO_USER;
  final: boolean;
}

export interface SystemMessage extends ChatMessage {
  direction: Direction.AGENT_TO_USER;
}

export interface ThinkingMessage extends Message {
  type: MessageType.THINKING;
  direction: Direction.AGENT_TO_USER;
  content: string;
}

export interface ToolCallMessage extends Message {
  type: MessageType.TOOL_CALL;
  direction: Direction.AGENT_TO_USER;
  tool_calls: ToolCallRequest[];
}

export interface ApprovalRequestMessage extends Message {
  type: MessageType.APPROVAL_REQUEST;
  direction: Direction.AGENT_TO_USER;
  tool_id: string;
  tool_name: string;
  tool_args: Record<string, any>;
  agent_id: string;  // Explicitly included
}

export interface ApprovalResponseMessage extends Message {
  type: MessageType.APPROVAL_RESPONSE;
  direction: Direction.USER_TO_AGENT;
  tool_id: string;
  decision: ApprovalDecision;
  feedback?: string;
  agent_id: string;  // Explicitly included
}

export interface ToolStartedMessage extends Message {
  type: MessageType.TOOL_STARTED;
  direction: Direction.AGENT_TO_USER;
  tool_id: string;
  tool_name: string;
}

export interface ToolResultMessage extends Message {
  type: MessageType.TOOL_RESULT;
  direction: Direction.AGENT_TO_USER;
  tool_id: string;
  tool_name: string;
  result: any;
}

export interface ToolErrorMessage extends Message {
  type: MessageType.TOOL_ERROR;
  direction: Direction.AGENT_TO_USER;
  tool_id: string;
  tool_name: string;
  error: string;
}

export interface UsageMessage extends Message {
  type: MessageType.USAGE;
  direction: Direction.AGENT_TO_USER;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface ErrorMessage extends Message {
  type: MessageType.ERROR;
  direction: Direction.AGENT_TO_USER;
  error: string;
  details?: Record<string, any>;
}

// Union type for all messages
export type AnyMessage = 
  | UserMessage
  | AgentMessage
  | SystemMessage
  | ThinkingMessage
  | ToolCallMessage
  | ApprovalRequestMessage
  | ApprovalResponseMessage
  | ToolStartedMessage
  | ToolResultMessage
  | ToolErrorMessage
  | UsageMessage
  | ErrorMessage;

// ============================================================================
// STREAMING RESPONSE TYPES
// ============================================================================

// StreamResponse is what the API actually sends over SSE
// The type can be any MessageType value OR the special 'complete' signal
export interface StreamResponse {
  type: 'chat' | 'thinking' | 'tool_call' | 'approval_request' | 'approval_response' | 
        'tool_started' | 'tool_result' | 'tool_error' | 'usage' | 'error' | 'complete';
  content: string;
  metadata?: Record<string, any>;
  timestamp?: string;
  session_id?: string;
  
  // Additional fields that might be present based on message type
  agent_id?: string;
  final?: boolean;
  tool_id?: string;
  tool_name?: string;
  tool_args?: Record<string, any>;
  tool_calls?: ToolCallRequest[];
  decision?: ApprovalDecision;
  feedback?: string;
  result?: any;
  error?: string;
  details?: Record<string, any>;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
}

// ============================================================================
// API ENDPOINT TYPES
// ============================================================================

export interface HealthCheck {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components?: {
    manager: string;
    agent: string;
    tools: string;
  };
  error?: string;
  timestamp: string;
}

export interface ServerInfo {
  name: string;
  version: string;
  status: string;
  timestamp: string;
}

// Tool decision endpoint types
export interface ToolDecisionRequest {
  tool_id: string;
  decision: 'approved' | 'rejected';
  feedback?: string;
  agent_id?: string;
}

export interface ToolDecisionResponse {
  success: boolean;
  tool_id: string;
  decision: string;
}

// Pending tools endpoint types
export interface PendingTool {
  tool_id: string;
  tool_name: string;
  tool_args: Record<string, any>;
  agent_id: string;
  created_at?: string;
  requires_approval: boolean;
}

export interface PendingToolsResponse {
  success: boolean;
  pending_tools: PendingTool[];
  count: number;
}

// Memory endpoint types
export interface ClearHistoryResponse {
  message: string;
}

// ============================================================================
// CLIENT CONFIGURATION
// ============================================================================

export interface ApiClientConfig {
  baseUrl?: string;
  timeout?: number;
  retryAttempts?: number;
  headers?: Record<string, string>;
}

// Export everything is already done above