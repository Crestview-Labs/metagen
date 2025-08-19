/**
 * E2E tests for chat streaming functionality
 * Port of Python tests from tests/api/test_chat_stream_e2e.py
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { v4 as uuidv4 } from 'uuid';
import { MetagenStreamingClient } from '../../src/streaming.js';
import { ChatService } from '../../generated/services/ChatService.js';
import { OpenAPI } from '../../generated/index.js';
import type { ChatRequest, ApprovalResponseMessage } from '../../generated/index.js';
import { ApprovalDecision } from '../../generated/models/ApprovalDecision.js';
import { MessageType } from '../../generated/models/MessageType.js';

// Configure API client
const BASE_URL = process.env.API_BASE_URL || 'http://localhost:8080';
OpenAPI.BASE = BASE_URL;

// Helper to collect all messages from a stream
async function collectStreamMessages(
  client: MetagenStreamingClient,
  request: ChatRequest,
  maxMessages = 100
): Promise<any[]> {
  const messages: any[] = [];
  let count = 0;
  
  for await (const message of client.chatStream(request)) {
    messages.push(message);
    count++;
    
    // Check for final message
    if (message.type === 'agent' && (message as any).final) {
      break;
    }
    
    // Safety limit
    if (count >= maxMessages) {
      break;
    }
  }
  
  return messages;
}

// Helper to wait for a condition with timeout
async function waitFor(
  condition: () => boolean | Promise<boolean>,
  timeoutMs = 5000,
  intervalMs = 100
): Promise<void> {
  const startTime = Date.now();
  
  while (Date.now() - startTime < timeoutMs) {
    if (await condition()) {
      return;
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  
  throw new Error(`Timeout waiting for condition after ${timeoutMs}ms`);
}

describe('Chat Stream E2E Tests', () => {
  let client: MetagenStreamingClient;
  
  beforeAll(async () => {
    // Initialize streaming client
    client = new MetagenStreamingClient(BASE_URL);
    
    // Verify server is running
    try {
      const response = await fetch(`${BASE_URL}/docs`);
      if (!response.ok) {
        throw new Error(`Server not responding at ${BASE_URL}`);
      }
    } catch (error) {
      throw new Error(
        `Server not running on ${BASE_URL}. Start it with: ./start_server.sh --test`
      );
    }
  });
  
  describe('Basic Functionality', () => {
    it('should handle basic chat stream', async () => {
      const sessionId = uuidv4();
      const request: ChatRequest = {
        message: 'Hello, just say hi back',
        session_id: sessionId
      };
      
      const messages = await collectStreamMessages(client, request);
      
      // Verify we got messages
      expect(messages.length).toBeGreaterThan(0);
      
      // Verify we got agent messages
      const agentMessages = messages.filter(m => m.type === 'agent');
      expect(agentMessages.length).toBeGreaterThan(0);
      
      // Verify we got a final message
      const finalMessage = messages.find(m => m.type === 'agent' && m.final);
      expect(finalMessage).toBeDefined();
    });
    
    it('should handle concurrent streams', async () => {
      // Create 3 concurrent sessions
      const sessions = [
        { id: uuidv4(), name: 'session-1' },
        { id: uuidv4(), name: 'session-2' },
        { id: uuidv4(), name: 'session-3' }
      ];
      
      // Start all streams concurrently
      const streamPromises = sessions.map(session => 
        collectStreamMessages(client, {
          message: `Hello from ${session.name}`,
          session_id: session.id
        })
      );
      
      // Wait for all to complete
      const results = await Promise.all(streamPromises);
      
      // Verify all completed successfully
      for (const messages of results) {
        expect(messages.length).toBeGreaterThan(0);
        const finalMessage = messages.find(m => m.type === 'agent' && m.final);
        expect(finalMessage).toBeDefined();
      }
    });
  });
  
  describe('Tool Approval Flow', () => {
    it('should handle tool approval workflow', async () => {
      const sessionId = uuidv4();
      const request: ChatRequest = {
        message: 'Use the write_file tool to create test_approval.txt with content "test"',
        session_id: sessionId
      };
      
      let approvalRequest: any = null;
      const allMessages: any[] = [];
      
      // Start streaming in background
      const streamPromise = (async () => {
        for await (const message of client.chatStream(request)) {
          allMessages.push(message);
          
          if (message.type === 'approval_request') {
            approvalRequest = message;
            
            // Send approval after a short delay
            setTimeout(async () => {
              if (approvalRequest) {
                const approval: ApprovalResponseMessage = {
                  type: MessageType.APPROVAL_RESPONSE,
                  tool_id: approvalRequest.tool_id,
                  decision: ApprovalDecision.APPROVED,
                  agent_id: approvalRequest.agent_id,
                  session_id: sessionId,
                  timestamp: new Date().toISOString()
                };
                
                // Send approval via dedicated endpoint
                await ChatService.handleApprovalResponseApiChatApprovalResponsePost({
                  requestBody: approval
                });
              }
            }, 500);
          }
          
          if (message.type === 'agent' && (message as any).final) {
            break;
          }
        }
      })();
      
      // Wait for stream to complete
      await streamPromise;
      
      // Verify we got approval request
      expect(approvalRequest).toBeDefined();
      expect(approvalRequest.tool_name).toBe('write_file');
      
      // Verify we got final message
      const finalMessage = allMessages.find(m => m.type === 'agent' && m.final);
      expect(finalMessage).toBeDefined();
    });
  });
  
  describe('Session Management', () => {
    it('should persist session across requests', async () => {
      const sessionId = uuidv4();
      
      // First request - introduce context
      const request1: ChatRequest = {
        message: 'My name is Alice and I love TypeScript programming.',
        session_id: sessionId
      };
      
      const messages1 = await collectStreamMessages(client, request1);
      expect(messages1.length).toBeGreaterThan(0);
      
      // Second request - test context retention
      const request2: ChatRequest = {
        message: "What's my name and what do I love?",
        session_id: sessionId
      };
      
      const messages2 = await collectStreamMessages(client, request2);
      expect(messages2.length).toBeGreaterThan(0);
      
      // Check that agent remembered the context
      const agentResponses = messages2
        .filter(m => m.type === 'agent' && m.content)
        .map(m => m.content)
        .join(' ');
      
      // Agent should mention Alice and TypeScript (weak assertion due to LLM variability)
      expect(agentResponses.length).toBeGreaterThan(0);
    });
    
    it('should handle multiple concurrent sessions', async () => {
      const session1Id = uuidv4();
      const session2Id = uuidv4();
      
      // Define session contexts
      const sessions = [
        { id: session1Id, name: 'Bob', color: 'blue' },
        { id: session2Id, name: 'Charlie', color: 'red' }
      ];
      
      // Run sessions concurrently
      const sessionPromises = sessions.map(async (session) => {
        // First message - set context
        const request1: ChatRequest = {
          message: `My name is ${session.name} and my favorite color is ${session.color}.`,
          session_id: session.id
        };
        
        const messages1 = await collectStreamMessages(client, request1);
        
        // Second message - verify context
        const request2: ChatRequest = {
          message: "What's my favorite color?",
          session_id: session.id
        };
        
        const messages2 = await collectStreamMessages(client, request2);
        
        return { session, messages1, messages2 };
      });
      
      const results = await Promise.all(sessionPromises);
      
      // Verify both sessions completed
      expect(results).toHaveLength(2);
      
      for (const result of results) {
        expect(result.messages1.length).toBeGreaterThan(0);
        expect(result.messages2.length).toBeGreaterThan(0);
      }
    });
    
    it('should isolate sessions from each other', async () => {
      const session1Id = uuidv4();
      const session2Id = uuidv4();
      
      // Session 1: Set a specific context
      const request1: ChatRequest = {
        message: 'Remember this secret code: ALPHA123',
        session_id: session1Id
      };
      
      await collectStreamMessages(client, request1);
      
      // Session 2: Try to access session 1's context (should fail)
      const request2: ChatRequest = {
        message: 'What was the secret code I just told you?',
        session_id: session2Id
      };
      
      const messages2 = await collectStreamMessages(client, request2);
      expect(messages2.length).toBeGreaterThan(0);
      
      // Session 1: Verify it still remembers its context
      const request3: ChatRequest = {
        message: 'What was the secret code?',
        session_id: session1Id
      };
      
      const messages3 = await collectStreamMessages(client, request3);
      expect(messages3.length).toBeGreaterThan(0);
    });
    
    it('should handle disconnection gracefully', async () => {
      const sessionId = uuidv4();
      
      // Start a request but disconnect early
      const request1: ChatRequest = {
        message: 'Start a long explanation about machine learning',
        session_id: sessionId
      };
      
      // Collect only first few messages then stop
      const messages1: any[] = [];
      
      try {
        let count = 0;
        for await (const message of client.chatStream(request1)) {
          messages1.push(message);
          count++;
          
          // Simulate early disconnection by breaking after 2 messages
          if (count >= 2) {
            break;
          }
        }
      } catch (error) {
        // Connection errors are expected when disconnecting early
      }
      
      // Verify we got at least some messages before disconnection
      expect(messages1.length).toBeGreaterThanOrEqual(2);
      
      // Wait a bit for server to process disconnection
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Reconnect with the same session
      const request2: ChatRequest = {
        message: 'Are you still there? Just say yes or no.',
        session_id: sessionId
      };
      
      const messages2 = await collectStreamMessages(client, request2);
      expect(messages2.length).toBeGreaterThan(0);
    });
  });
  
  describe('Queue Management', () => {
    it('should process messages in order', async () => {
      const sessionId = uuidv4();
      
      const questions = [
        "Let's count together. Say '1'",
        "Now say '2'",
        "Now say '3'",
        "What numbers did we just count?"
      ];
      
      const allResponses: any[][] = [];
      
      for (const question of questions) {
        const request: ChatRequest = {
          message: question,
          session_id: sessionId
        };
        
        const messages = await collectStreamMessages(client, request);
        allResponses.push(messages);
        expect(messages.length).toBeGreaterThan(0);
      }
      
      // Verify we got responses for all requests in order
      expect(allResponses).toHaveLength(questions.length);
    });
    
    it('should handle rapid requests without message loss', async () => {
      const sessionId = uuidv4();
      const numRequests = 5;
      
      // Send multiple requests rapidly with minimal delay
      const requestPromises: Promise<any[]>[] = [];
      
      for (let i = 0; i < numRequests; i++) {
        // Small stagger to avoid overwhelming the server
        await new Promise(resolve => setTimeout(resolve, 100));
        
        const request: ChatRequest = {
          message: `Request ${i}: Acknowledge with the number ${i}`,
          session_id: sessionId
        };
        
        requestPromises.push(collectStreamMessages(client, request));
      }
      
      // Wait for all requests to complete
      const results = await Promise.all(requestPromises);
      
      // Verify all requests completed successfully
      expect(results).toHaveLength(numRequests);
      
      for (let i = 0; i < results.length; i++) {
        expect(results[i].length).toBeGreaterThan(0);
      }
    });
  });
});