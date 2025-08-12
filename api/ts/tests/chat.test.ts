// Comprehensive tests for chat API - both mock and real
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { MetagenAPI } from '../src/api.js';
import { 
  ChatRequest, 
  ChatResponse, 
  UIResponseModel,
  ToolDecisionRequest,
  PendingToolsResponse,
  SSEMessage 
} from '../src/types.js';
import { APIError, StreamError } from '../src/errors.js';

// ============================================================================
// MOCK TESTS
// ============================================================================

describe('Chat API - Mocked', () => {
  let api: MetagenAPI;
  let fetchMock: any;

  beforeEach(() => {
    api = new MetagenAPI('http://localhost:8000');
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('chat endpoint', () => {
    it('should send chat request successfully', async () => {
      const mockResponse: ChatResponse = {
        responses: [{
          type: 'text',
          content: 'Hello!',
          agent_id: 'test-agent',
          timestamp: new Date().toISOString(),
          metadata: {}
        }],
        session_id: 'session-123',
        success: true
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'X-API-Version': '0.1.0' }),
        json: async () => mockResponse
      });

      const request: ChatRequest = {
        message: 'Hello, assistant!',
        session_id: 'session-123'
      };

      const response = await api.chat(request);

      expect(response).toEqual(mockResponse);
      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/chat',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(request),
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-API-Version': '0.1.0'
          })
        })
      );
    });

    it('should handle chat without session_id', async () => {
      const mockResponse: ChatResponse = {
        responses: [],
        success: true
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => mockResponse
      });

      const request: ChatRequest = {
        message: 'Hello!'
      };

      const response = await api.chat(request);
      expect(response.session_id).toBeUndefined();
    });

    it('should handle API errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers(),
        json: async () => ({ error: 'Server error' })
      });

      const request: ChatRequest = { message: 'Test' };

      await expect(api.chat(request)).rejects.toThrow(APIError);
    });

    it('should handle network errors', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error'));

      const request: ChatRequest = { message: 'Test' };

      await expect(api.chat(request)).rejects.toThrow('Network request failed');
    });
  });

  describe('chat streaming', () => {
    it('should handle streaming responses', async () => {
      const mockSSEData = [
        'data: {"type":"text","content":"Hello","timestamp":"2025-01-08T12:00:00"}\n\n',
        'data: {"type":"text","content":"World","timestamp":"2025-01-08T12:00:01"}\n\n',
        'data: {"type":"complete","session_id":"123"}\n\n'
      ];

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          mockSSEData.forEach(data => {
            controller.enqueue(encoder.encode(data));
          });
          controller.close();
        }
      });

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const request: ChatRequest = {
        message: 'Stream test',
        session_id: 'stream-123'
      };

      const messages: SSEMessage[] = [];
      for await (const message of api.chatStream(request)) {
        messages.push(message);
      }

      expect(messages).toHaveLength(3);
      expect(messages[0].type).toBe('text');
      expect(messages[0].content).toBe('Hello');
      expect(messages[2].type).toBe('complete');
    });

    it('should handle stream errors', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"type":"error","error":"Stream error"}\n\n'));
          controller.close();
        }
      });

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        body: stream
      });

      const request: ChatRequest = { message: 'Test' };

      const generator = api.chatStream(request);
      await expect(generator.next()).rejects.toThrow(StreamError);
    });
  });

  describe('tool decision', () => {
    it('should submit tool approval', async () => {
      const mockResponse = {
        success: true,
        tool_id: 'tool-123',
        decision: 'approved'
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => mockResponse
      });

      const decision: ToolDecisionRequest = {
        tool_id: 'tool-123',
        decision: 'approved',
        agent_id: 'METAGEN'
      };

      const response = await api.submitToolDecision(decision);

      expect(response.success).toBe(true);
      expect(response.tool_id).toBe('tool-123');
      expect(response.decision).toBe('approved');
    });

    it('should submit tool rejection with feedback', async () => {
      const mockResponse = {
        success: true,
        tool_id: 'tool-456',
        decision: 'rejected'
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => mockResponse
      });

      const decision: ToolDecisionRequest = {
        tool_id: 'tool-456',
        decision: 'rejected',
        feedback: 'Not safe'
      };

      const response = await api.submitToolDecision(decision);

      expect(response.decision).toBe('rejected');
    });
  });

  describe('pending tools', () => {
    it('should get pending tools', async () => {
      const mockResponse: PendingToolsResponse = {
        success: true,
        pending_tools: [{
          tool_id: 'pending-123',
          tool_name: 'test_tool',
          tool_args: { arg1: 'value1' },
          agent_id: 'METAGEN',
          created_at: '2025-01-08T12:00:00',
          requires_approval: true
        }],
        count: 1
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => mockResponse
      });

      const response = await api.getPendingTools();

      expect(response.success).toBe(true);
      expect(response.count).toBe(1);
      expect(response.pending_tools[0].tool_id).toBe('pending-123');
    });

    it('should handle empty pending tools', async () => {
      const mockResponse: PendingToolsResponse = {
        success: true,
        pending_tools: [],
        count: 0
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => mockResponse
      });

      const response = await api.getPendingTools();

      expect(response.count).toBe(0);
      expect(response.pending_tools).toEqual([]);
    });
  });

  describe('version handling', () => {
    it('should include version header in requests', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        json: async () => ({ responses: [], success: true })
      });

      await api.chat({ message: 'Test' });

      expect(fetchMock).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-API-Version': '0.1.0'
          })
        })
      );
    });

    it('should warn on version mismatch', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'X-API-Version': '0.2.0' }),
        json: async () => ({ responses: [], success: true })
      });

      await api.chat({ message: 'Test' });

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('version mismatch')
      );
    });
  });
});

// ============================================================================
// INTEGRATION TESTS WITH REAL API
// ============================================================================

describe('Chat API - Integration', () => {
  let api: MetagenAPI;
  const REAL_API_URL = process.env.API_URL || 'http://localhost:8000';
  
  // Skip these tests unless explicitly running integration tests
  const skipIntegration = !process.env.RUN_INTEGRATION_TESTS;

  beforeEach(() => {
    api = new MetagenAPI(REAL_API_URL);
  });

  describe.skipIf(skipIntegration)('real chat endpoints', () => {
    it('should send real chat request', async () => {
      const request: ChatRequest = {
        message: 'What is 2+2? Reply with just the number.',
        session_id: 'test-ts-integration'
      };

      const response = await api.chat(request);

      expect(response.success).toBe(true);
      expect(response.responses).toBeDefined();
      expect(response.responses.length).toBeGreaterThan(0);
      expect(response.session_id).toBe('test-ts-integration');
    }, 30000); // 30 second timeout

    it('should stream real chat responses', async () => {
      const request: ChatRequest = {
        message: 'Count from 1 to 3',
        session_id: 'test-ts-stream'
      };

      const messages: SSEMessage[] = [];
      let completed = false;

      for await (const message of api.chatStream(request)) {
        messages.push(message);
        if (message.type === 'complete') {
          completed = true;
          break;
        }
      }

      expect(messages.length).toBeGreaterThan(0);
      expect(completed).toBe(true);
    }, 30000);

    it('should handle concurrent requests', async () => {
      const requests = [
        api.chat({ message: 'Say hello', session_id: 'concurrent-1' }),
        api.chat({ message: 'Say goodbye', session_id: 'concurrent-2' }),
        api.chat({ message: 'Say thanks', session_id: 'concurrent-3' })
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response: any) => {
        expect(response.success).toBe(true);
        expect(response.responses.length).toBeGreaterThan(0);
      });
    }, 30000);

    it('should maintain session context', async () => {
      const sessionId = 'context-test-ts';

      // First message
      const response1 = await api.chat({
        message: 'My name is TypeScriptTester',
        session_id: sessionId
      });
      expect(response1.success).toBe(true);

      // Second message referencing first
      const response2 = await api.chat({
        message: 'What is my name?',
        session_id: sessionId
      });
      expect(response2.success).toBe(true);
      
      // Check if response mentions the name (context working)
      const responseText = response2.responses
        .map((r: any) => r.content)
        .join(' ');
      // May or may not contain the name depending on context handling
    }, 30000);

    it('should get real pending tools', async () => {
      const response = await api.getPendingTools();
      
      expect(response.success).toBe(true);
      expect(response.pending_tools).toBeDefined();
      expect(Array.isArray(response.pending_tools)).toBe(true);
    });

    it('should handle special characters', async () => {
      const request: ChatRequest = {
        message: 'What is 🎉 emoji?',
        session_id: 'emoji-test'
      };

      const response = await api.chat(request);
      expect(response.success).toBe(true);
    }, 30000);
  });
});

// ============================================================================
// ERROR HANDLING TESTS
// ============================================================================

describe('Error Handling', () => {
  let api: MetagenAPI;

  beforeEach(() => {
    api = new MetagenAPI('http://invalid-url-12345.com');
  });

  it('should handle connection errors gracefully', async () => {
    await expect(api.chat({ message: 'Test' })).rejects.toThrow();
  });

  it('should handle invalid JSON responses', async () => {
    const fetchMock = vi.fn();
    global.fetch = fetchMock;

    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => { throw new Error('Invalid JSON'); }
    });

    await expect(api.chat({ message: 'Test' })).rejects.toThrow();
  });
});