// Auto-generated SSE/streaming utilities - DO NOT EDIT

import { SSEMessage } from './types';
import { StreamError } from './errors';

export interface StreamOptions {
  signal?: AbortSignal;
  onMessage?: (message: SSEMessage) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

export class SSEParser {
  private buffer = '';

  parse(chunk: string): SSEMessage[] {
    this.buffer += chunk;
    const messages: SSEMessage[] = [];
    const lines = this.buffer.split('\n');
    
    let i = 0;
    while (i < lines.length - 1) {
      const line = lines[i];
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        try {
          const message = JSON.parse(data) as SSEMessage;
          messages.push(message);
        } catch (e) {
          console.error('Failed to parse SSE message:', data, e);
        }
        // Skip the empty line after data
        if (lines[i + 1] === '') {
          i++;
        }
      }
      i++;
    }
    
    // Keep the last incomplete line in buffer
    this.buffer = lines[lines.length - 1];
    
    return messages;
  }
  
  reset() {
    this.buffer = '';
  }
}

export async function* parseSSEStream(
  response: Response,
  options?: StreamOptions
): AsyncGenerator<SSEMessage, void, unknown> {
  if (!response.body) {
    throw new StreamError('Response body is null');
  }
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();
  
  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) {
        options?.onComplete?.();
        break;
      }
      
      const chunk = decoder.decode(value, { stream: true });
      const messages = parser.parse(chunk);
      
      for (const message of messages) {
        if (message.type === 'error') {
          const error = new StreamError(message.error || 'Unknown error');
          options?.onError?.(error);
          throw error;
        }
        
        if (message.type === 'complete') {
          options?.onComplete?.();
          return;
        }
        
        options?.onMessage?.(message);
        yield message;
      }
    }
  } catch (error) {
    if (error instanceof Error) {
      options?.onError?.(error);
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}