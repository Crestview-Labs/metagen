/**
 * Unit tests for MetagenAPI
 * Tests basic API functionality without requiring a running server
 */

import XCTest
import Foundation
@testable import MetagenAPI

final class APITests: XCTestCase {
    
    func testStreamingClientCreation() throws {
        // Test default URL
        let client1 = try MetagenStreamingClient()
        XCTAssertNotNil(client1)
        
        // Test custom URL
        let client2 = try MetagenStreamingClient(baseURL: "http://localhost:3000")
        XCTAssertNotNil(client2)
    }
    
    func testAPIVersionInfo() {
        // Verify version info is available
        XCTAssertNotNil(APIVersion.version)
        XCTAssertFalse(APIVersion.version.isEmpty)
        
        XCTAssertNotNil(APIVersion.generatedAt)
        XCTAssertFalse(APIVersion.generatedAt.isEmpty)
    }
    
    func testGeneratedTypesAvailable() {
        // Verify that key types are available from the generated code
        
        // Test ChatRequest structure
        let chatRequest = Components.Schemas.ChatRequest(
            message: Components.Schemas.ChatRequest.messagePayload(value1: "Test message"),
            session_id: "test-session"
        )
        XCTAssertEqual(chatRequest.session_id, "test-session")
        
        // Test MessageType enum
        let messageTypes: [Components.Schemas.MessageType] = [
            .user,
            .agent,
            .system,
            .thinking,
            .tool_call
        ]
        XCTAssertEqual(messageTypes.count, 5)
        
        // Test ApprovalDecision enum
        let approvalDecisions: [Components.Schemas.ApprovalDecision] = [
            .approved,
            .rejected
        ]
        XCTAssertEqual(approvalDecisions.count, 2)
    }
    
    func testChatRequestInitialization() {
        // Test with string message
        let request1 = Components.Schemas.ChatRequest(
            message: Components.Schemas.ChatRequest.messagePayload(value1: "Hello world"),
            session_id: "session-123"
        )
        XCTAssertNotNil(request1.message.value1)
        XCTAssertEqual(request1.message.value1, "Hello world")
        XCTAssertEqual(request1.session_id, "session-123")
        
        // Test with UserMessage
        let userMessage = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: nil,
            agent_id: "test-agent",
            session_id: "session-456",
            content: "User message content"
        )
        
        let request2 = Components.Schemas.ChatRequest(
            message: Components.Schemas.ChatRequest.messagePayload(value2: userMessage),
            session_id: "session-456"
        )
        XCTAssertNotNil(request2.message.value2)
        XCTAssertEqual(request2.message.value2?.content, "User message content")
    }
    
    func testApprovalResponseMessage() {
        let approvalMessage = Components.Schemas.ApprovalResponseMessage(
            _type: .approval_response,
            timestamp: nil,
            agent_id: "agent-123",
            session_id: "session-789",
            tool_id: "tool-456",
            decision: .approved
        )
        
        XCTAssertEqual(approvalMessage._type, .approval_response)
        XCTAssertEqual(approvalMessage.tool_id, "tool-456")
        XCTAssertEqual(approvalMessage.decision, Components.Schemas.ApprovalDecision.approved)
        XCTAssertEqual(approvalMessage.session_id, "session-789")
    }
    
    func testURLConstruction() throws {
        // Test that URLs are properly constructed
        let baseURL = "http://localhost:8080"
        let _ = try MetagenStreamingClient(baseURL: baseURL)
        
        // We can't directly test the URL construction in the private method,
        // but we can verify the client initializes correctly with various URLs
        let testURLs = [
            "http://localhost:8000",
            "http://127.0.0.1:8080",
            "https://api.example.com",
            "http://api.example.com:3000"
        ]
        
        for urlString in testURLs {
            let testClient = try MetagenStreamingClient(baseURL: urlString)
            XCTAssertNotNil(testClient)
        }
    }
}