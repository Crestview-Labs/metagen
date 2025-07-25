// API Types - Match Python backend Pydantic models

export interface ChatRequest {
  message: string;
  metadata?: Record<string, any>;
}

export interface UIResponseModel {
  type: 'text' | 'error' | 'tool_result' | 'command_result';
  content: string;
  metadata?: Record<string, any>;
}

export interface ChatResponse {
  responses: UIResponseModel[];
  session_id: string;
  timestamp: string;
}

export interface StreamResponse {
  type: 'text' | 'error' | 'tool_call' | 'tool_result' | 'thinking' | 'system' | 'complete';
  content: string;
  metadata?: Record<string, any>;
  timestamp?: string;
  session_id?: string;
}

export interface AuthStatus {
  authenticated: boolean;
  user_id?: string;
  email?: string;
  expires_at?: string;
}

export interface AuthLoginRequest {
  redirect_uri?: string;
  force?: boolean;
}

export interface AuthLoginResponse {
  auth_url: string;
  message: string;
}

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

// Error response type
export interface ErrorResponse {
  detail: string;
  type?: string;
}

// API Client configuration
export interface ApiClientConfig {
  baseUrl?: string;
  timeout?: number;
  retryAttempts?: number;
}