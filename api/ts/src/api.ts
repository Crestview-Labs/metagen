// Auto-generated API client - DO NOT EDIT

import { API_VERSION } from './version';
import * as types from './types';
import { APIError, NetworkError } from './errors';
import { parseSSEStream, StreamOptions } from './streaming';

export class MetagenAPI {
  constructor(private baseURL: string = 'http://localhost:8000') {}

  // =================
  // Chat endpoints
  // =================
  
  async chat(request: types.ChatRequest): Promise<types.ChatResponse> {
    const response = await this.fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify(request)
    });
    return response.json();
  }

  async *chatStream(
    request: types.ChatRequest,
    options?: StreamOptions
  ): AsyncGenerator<types.SSEMessage, void, unknown> {
    const response = await this.fetch('/api/chat/stream', {
      method: 'POST',
      body: JSON.stringify(request),
      headers: {
        'Accept': 'text/event-stream',
      }
    }, false); // Don't check response.ok for streaming
    
    yield* parseSSEStream(response, options);
  }

  async submitToolDecision(decision: types.ToolDecisionRequest): Promise<types.ToolDecisionResponse> {
    const response = await this.fetch('/api/tool-decision', {
      method: 'POST',
      body: JSON.stringify(decision)
    });
    return response.json();
  }

  async getPendingTools(): Promise<types.PendingToolsResponse> {
    const response = await this.fetch('/api/pending-tools', {
      method: 'GET'
    });
    return response.json();
  }

  // =================
  // Auth endpoints
  // =================
  
  async getAuthStatus(): Promise<types.AuthStatus> {
    const response = await this.fetch('/api/auth/status', {
      method: 'GET'
    });
    return response.json();
  }

  async login(request: types.AuthLoginRequest = {}): Promise<types.AuthResponse> {
    const response = await this.fetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(request)
    });
    return response.json();
  }

  async logout(): Promise<types.AuthResponse> {
    const response = await this.fetch('/api/auth/logout', {
      method: 'POST'
    });
    return response.json();
  }

  // =================
  // System endpoints
  // =================
  
  async getSystemInfo(): Promise<types.SystemInfo> {
    const response = await this.fetch('/api/system/info', {
      method: 'GET'
    });
    return response.json();
  }

  async getHealthCheck(): Promise<types.HealthCheckResponse> {
    const response = await this.fetch('/api/system/health', {
      method: 'GET'
    });
    return response.json();
  }

  // =================
  // Tools endpoints
  // =================
  
  async getTools(): Promise<types.ToolsResponse> {
    const response = await this.fetch('/api/tools', {
      method: 'GET'
    });
    return response.json();
  }

  async getGoogleTools(): Promise<types.GoogleToolsResponse> {
    const response = await this.fetch('/api/tools/google', {
      method: 'GET'
    });
    return response.json();
  }

  // =================
  // Memory endpoints
  // =================
  
  async clearMemory(): Promise<types.ClearMemoryResponse> {
    const response = await this.fetch('/api/memory/clear', {
      method: 'POST'
    });
    return response.json();
  }

  // =================
  // Telemetry endpoints
  // =================
  
  async getRecentTraces(limit: number = 20): Promise<string[]> {
    const response = await this.fetch(`/api/telemetry/traces?limit=${limit}`, {
      method: 'GET'
    });
    return response.json();
  }

  async getTrace(traceId: string): Promise<types.TraceResponse> {
    const response = await this.fetch(`/api/telemetry/traces/${traceId}`, {
      method: 'GET'
    });
    return response.json();
  }

  async analyzeTrace(traceId: string): Promise<any> {
    const response = await this.fetch(`/api/telemetry/traces/${traceId}/analysis`, {
      method: 'GET'
    });
    return response.json();
  }

  async getTraceInsights(traceId: string): Promise<types.TraceInsightsResponse> {
    const response = await this.fetch(`/api/telemetry/traces/${traceId}/insights`, {
      method: 'GET'
    });
    return response.json();
  }

  async getTraceReport(traceId: string): Promise<types.TraceReportResponse> {
    const response = await this.fetch(`/api/telemetry/traces/${traceId}/report`, {
      method: 'GET'
    });
    return response.json();
  }

  async getCurrentTrace(): Promise<types.CurrentTraceResponse> {
    const response = await this.fetch('/api/telemetry/debug/current', {
      method: 'GET'
    });
    return response.json();
  }

  async getMemoryTraces(limit: number = 10): Promise<string[]> {
    const response = await this.fetch(`/api/telemetry/memory/traces?limit=${limit}`, {
      method: 'GET'
    });
    return response.json();
  }

  async getMemoryTrace(traceId: string): Promise<types.TraceResponse> {
    const response = await this.fetch(`/api/telemetry/memory/traces/${traceId}`, {
      method: 'GET'
    });
    return response.json();
  }

  async getLatestTraceInsights(): Promise<types.TraceInsightsResponse> {
    const response = await this.fetch('/api/telemetry/latest/insights', {
      method: 'GET'
    });
    return response.json();
  }

  async getLatestTraceReport(): Promise<types.TraceReportResponse> {
    const response = await this.fetch('/api/telemetry/latest/report', {
      method: 'GET'
    });
    return response.json();
  }

  // =================
  // Private methods
  // =================
  
  private async fetch(path: string, options?: RequestInit, checkOk: boolean = true): Promise<Response> {
    try {
      const response = await fetch(`${this.baseURL}${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'X-API-Version': API_VERSION,
          ...options?.headers,
        }
      });

      // Check version mismatch
      const responseVersion = response.headers.get('X-API-Version');
      if (responseVersion && responseVersion !== API_VERSION) {
        console.warn(`API version mismatch: expected ${API_VERSION}, received ${responseVersion}`);
      }

      if (checkOk && !response.ok) {
        let body;
        try {
          body = await response.json();
        } catch {
          body = await response.text();
        }
        throw new APIError(response.status, response.statusText, body);
      }

      return response;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new NetworkError('Network request failed', error as Error);
    }
  }
}

// Export a default instance
export const api = new MetagenAPI();