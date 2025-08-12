// Auto-generated from api/models - DO NOT EDIT

// From api/models/chat.py
export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface UIResponseModel {
  type: string;
  content: string;
  agent_id: string;
  metadata?: Record<string, any>;
  timestamp: string;  // ISO datetime string
}

export interface ChatResponse {
  responses: UIResponseModel[];
  session_id?: string;
  success: boolean;
}

// From api/models/auth.py
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

// From api/models/system.py
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

// From api/models/common.py
export interface ErrorResponse {
  error: string;
  error_type?: string;
  timestamp: string;  // ISO datetime string
}

export interface SuccessResponse {
  message: string;
  data?: Record<string, any>;
  timestamp: string;  // ISO datetime string
}

// Additional types from route analysis
export interface ToolDecisionRequest {
  tool_id: string;
  decision: "approved" | "rejected";
  feedback?: string;
  agent_id?: string;
}

export interface ToolDecisionResponse {
  success: boolean;
  tool_id: string;
  decision: string;
}

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

export interface HealthCheckResponse {
  status: "healthy" | "degraded" | "unhealthy";
  components?: {
    manager: string;
    agent: string;
    tools: string;
  };
  error?: string;
  timestamp: string;
}

export interface GoogleToolsResponse {
  count: number;
  tools: any[];
  services: {
    gmail: any[];
    drive: any[];
    calendar: any[];
  };
}

export interface ClearMemoryResponse {
  message: string;
  conversation_turns_deleted: string;
  telemetry_spans_deleted: string;
}

export interface TraceResponse {
  trace_id: string;
  spans: any[];
}

export interface TraceInsightsResponse {
  trace_id: string;
  insights: Record<string, any>;
}

export interface TraceReportResponse {
  trace_id: string;
  report: string;
}

export interface CurrentTraceResponse {
  status?: string;
  trace_id?: string;
  span_id?: string;
  is_recording?: boolean;
  span_name?: string;
}

// SSE event types for streaming
export interface SSEMessage {
  type: string;
  content?: string;
  agent_id?: string;
  metadata?: Record<string, any>;
  timestamp?: string;
  session_id?: string;
  error?: string;
}