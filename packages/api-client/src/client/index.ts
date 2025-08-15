import axios, { AxiosInstance, AxiosResponse } from 'axios';
import {
  ApiClientConfig,
  ChatRequest,
  ChatResponse,
  StreamResponse,
  AuthStatus,
  AuthLoginRequest,
  AuthLoginResponse,
  ToolsResponse,
  SystemInfo,
  HealthCheck,
  ServerInfo,
  ErrorResponse,
  ApprovalResponseMessage
} from '../types/index.js';

export class MetagenApiClient {
  private api: AxiosInstance;
  private sessionId: string;
  
  constructor(config: ApiClientConfig = {}) {
    const {
      baseUrl = 'http://127.0.0.1:8080',
      timeout = 30000,
      retryAttempts = 3,
      sessionId
    } = config;
    
    // Generate session ID if not provided
    this.sessionId = sessionId || this.generateSessionId();
    
    this.api = axios.create({
      baseURL: baseUrl,
      timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    // Add response interceptor for error handling
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.data?.detail) {
          throw new Error(error.response.data.detail);
        }
        throw error;
      }
    );
  }

  // Generate a unique session ID for this client instance
  private generateSessionId(): string {
    // Use crypto.randomUUID if available (Node.js 14.17+, modern browsers)
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    // Fallback to manual UUID v4 generation
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  // Get the current session ID
  getSessionId(): string {
    return this.sessionId;
  }

  // Server endpoints
  async getServerInfo(): Promise<ServerInfo> {
    const response: AxiosResponse<ServerInfo> = await this.api.get('/');
    return response.data;
  }

  async getHealth(): Promise<HealthCheck> {
    const response: AxiosResponse<HealthCheck> = await this.api.get('/health');
    return response.data;
  }

  // Chat endpoints
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    // Add session_id to the request
    const requestWithSession = { ...request, session_id: this.sessionId };
    const response: AxiosResponse<ChatResponse> = await this.api.post('/api/chat', requestWithSession);
    return response.data;
  }

  async *sendMessageStream(request: ChatRequest): AsyncGenerator<StreamResponse, void, unknown> {
    try {
      // Add session_id to the request
      const requestWithSession = { ...request, session_id: this.sessionId };
      const response = await fetch(`${this.api.defaults.baseURL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestWithSession),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Stream error response:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body reader available');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              // Debug logging
              if (process.env.METAGEN_DEBUG) {
                console.error('Stream data:', data);
              }
              yield data as StreamResponse;
            } catch (error) {
              console.warn('Failed to parse stream data:', line, error);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
    } catch (error) {
      console.error('Stream request error:', error);
      throw error;
    }
  }

  // Authentication endpoints
  async getAuthStatus(): Promise<AuthStatus> {
    const response: AxiosResponse<AuthStatus> = await this.api.get('/api/auth/status');
    return response.data;
  }

  async login(force?: boolean): Promise<AuthLoginResponse> {
    const request: AuthLoginRequest = force ? { force: true } : {};
    const response: AxiosResponse<AuthLoginResponse> = await this.api.post('/api/auth/login', request);
    return response.data;
  }

  async logout(): Promise<{ message: string }> {
    const response: AxiosResponse<{ message: string }> = await this.api.post('/api/auth/logout');
    return response.data;
  }

  // Tools endpoints
  async getTools(): Promise<ToolsResponse> {
    const response: AxiosResponse<ToolsResponse> = await this.api.get('/api/tools');
    return response.data;
  }

  async getGoogleTools(): Promise<ToolsResponse> {
    const response: AxiosResponse<ToolsResponse> = await this.api.get('/api/tools/google');
    return response.data;
  }

  // Memory endpoints
  async clearHistory(): Promise<{ message: string }> {
    const response: AxiosResponse<{ message: string }> = await this.api.post('/api/memory/clear');
    return response.data;
  }

  // System endpoints
  async getSystemInfo(): Promise<SystemInfo> {
    const response: AxiosResponse<SystemInfo> = await this.api.get('/api/system/info');
    return response.data;
  }

  async getSystemHealth(): Promise<HealthCheck> {
    const response: AxiosResponse<HealthCheck> = await this.api.get('/api/system/health');
    return response.data;
  }

  // Tool approval endpoints
  async sendToolDecision(decision: ApprovalResponseMessage): Promise<{ success: boolean; tool_id: string; decision: string }> {
    const response: AxiosResponse<{ success: boolean; tool_id: string; decision: string }> = await this.api.post('/api/tool-decision', decision);
    return response.data;
  }

  async getPendingTools(): Promise<{ success: boolean; pending_tools: Array<any>; count: number }> {
    const response: AxiosResponse<{ success: boolean; pending_tools: Array<any>; count: number }> = await this.api.get('/api/pending-tools');
    return response.data;
  }

  // Utility methods
  async isServerHealthy(): Promise<boolean> {
    try {
      const health = await this.getHealth();
      return health.status === 'healthy';
    } catch {
      return false;
    }
  }

  async isAuthenticated(): Promise<boolean> {
    try {
      const auth = await this.getAuthStatus();
      return auth.authenticated;
    } catch {
      return false;
    }
  }
}

// Export default instance
export const apiClient = new MetagenApiClient();

// Export types for convenience
export * from '../types/index.js';