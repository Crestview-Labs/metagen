/**
 * SSE Streaming wrapper for Metagen API v2025.08.19.152833
 * Generated: 2025-08-19T15:28:35.118767+00:00
 */

import { OpenAPI } from '../generated/index.js';
import type { ChatRequest } from '../generated/index.js';

export interface StreamOptions {
  signal?: AbortSignal;
  onError?: (error: Error) => void;
  retryDelay?: number;
}

export interface SSEMessage {
  id?: string;
  event?: string;
  data: string;
  retry?: number;
}

export async function* parseSSEStream(
  response: Response,
  options?: StreamOptions
): AsyncGenerator<SSEMessage, void, unknown> {
  if (!response.body) {
    throw new Error('Response body is empty');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim() === '') continue;
        
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            return;
          }
          
          yield {
            data,
            event: 'message'
          };
        }
      }
    }
  } catch (error) {
    if (options?.onError) {
      options.onError(error as Error);
    } else {
      throw error;
    }
  } finally {
    reader.releaseLock();
  }
}

export class MetagenStreamingClient {
  private baseURL: string;
  
  constructor(baseURL: string = 'http://localhost:8080') {
    this.baseURL = baseURL;
    OpenAPI.BASE = baseURL;
  }
  
  /**
   * Stream chat responses using Server-Sent Events
   */
  async *chatStream(request: ChatRequest): AsyncGenerator<any, void, unknown> {
    const response = await fetch(`${this.baseURL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    for await (const sseMessage of parseSSEStream(response)) {
      try {
        const data = JSON.parse(sseMessage.data);
        yield data;
        if (data.type === 'complete') return;
      } catch (e) {
        console.warn('Failed to parse SSE data:', sseMessage.data);
      }
    }
  }
}

export const VERSION = '2025.08.19.152833';
