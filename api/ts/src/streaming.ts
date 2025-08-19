/**
 * SSE Streaming wrapper for Metagen API v0.1.1
 * Generated: 2025-08-19T21:14:18.851410+00:00
 */

import { OpenAPI, ChatService } from '../generated/index.js';
import type { ChatRequest, CancelablePromise } from '../generated/index.js';

export interface StreamOptions {
  signal?: AbortSignal;
  onError?: (error: Error) => void;
  retryDelay?: number;
}

// Extract the SSE message type from the generated service
// This extracts the union type from the ChatService.chatStreamApiChatStreamPost return type
type ExtractPromiseType<T> = T extends CancelablePromise<infer U> ? U : never;
type ChatStreamReturnType = ReturnType<typeof ChatService.chatStreamApiChatStreamPost>;
export type SSEMessage = ExtractPromiseType<ChatStreamReturnType>;

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
          
          try {
            const message = JSON.parse(data) as SSEMessage;
            yield message;
          } catch (e) {
            console.warn('Failed to parse SSE data:', data);
          }
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
  async *chatStream(request: ChatRequest): AsyncGenerator<SSEMessage, void, unknown> {
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

    for await (const message of parseSSEStream(response)) {
      yield message;
      // Check if this is an AgentMessage with final flag set
      if (message.type === 'agent' && (message as any).final) {
        return;
      }
    }
  }
}

export const VERSION = '0.1.1';
