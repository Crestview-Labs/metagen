/**
 * Unit tests for Chat functionality
 * Tests chat-related types and functions without requiring a server
 */

import XCTest
import Foundation
@testable import MetagenAPI

final class ChatTests: XCTestCase {
    
    func testMessageTypeEnumeration() {
        // Test all message types are available
        let allTypes = Components.Schemas.MessageType.allCases
        
        // Verify we have the expected message types
        XCTAssertTrue(allTypes.contains(.user))
        XCTAssertTrue(allTypes.contains(.agent))
        XCTAssertTrue(allTypes.contains(.system))
        XCTAssertTrue(allTypes.contains(.thinking))
        XCTAssertTrue(allTypes.contains(.tool_call))
        
        // Test raw values
        XCTAssertEqual(Components.Schemas.MessageType.user.rawValue, "user")
        XCTAssertEqual(Components.Schemas.MessageType.agent.rawValue, "agent")
        XCTAssertEqual(Components.Schemas.MessageType.tool_call.rawValue, "tool_call")
    }
    
    func testChatRequestPayloadVariants() {
        // Test that ChatRequest can handle different message types
        
        // Variant 1: Plain string message
        let stringPayload = Components.Schemas.ChatRequest.messagePayload(
            value1: "Simple message"
        )
        XCTAssertNotNil(stringPayload.value1)
        XCTAssertNil(stringPayload.value2)
        XCTAssertNil(stringPayload.value3)
        
        // Variant 2: UserMessage
        let userMessage = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: nil,
            agent_id: "METAGEN",
            session_id: "test-session",
            content: "User message"
        )
        let userPayload = Components.Schemas.ChatRequest.messagePayload(
            value2: userMessage
        )
        XCTAssertNil(userPayload.value1)
        XCTAssertNotNil(userPayload.value2)
        XCTAssertNil(userPayload.value3)
        
        // Variant 3: ApprovalResponseMessage
        let approvalMessage = Components.Schemas.ApprovalResponseMessage(
            _type: .approval_response,
            timestamp: nil,
            agent_id: "USER",
            session_id: "test-session",
            tool_id: "tool-123",
            decision: .approved
        )
        let approvalPayload = Components.Schemas.ChatRequest.messagePayload(
            value3: approvalMessage
        )
        XCTAssertNil(approvalPayload.value1)
        XCTAssertNil(approvalPayload.value2)
        XCTAssertNotNil(approvalPayload.value3)
    }
    
    func testApprovalDecisionTypes() {
        // Test all approval decision types
        let decisions: [Components.Schemas.ApprovalDecision] = [
            .approved,
            .rejected
        ]
        
        XCTAssertEqual(decisions.count, 2)
        
        // Test raw values
        XCTAssertEqual(Components.Schemas.ApprovalDecision.approved.rawValue, "approved")
        XCTAssertEqual(Components.Schemas.ApprovalDecision.rejected.rawValue, "rejected")
    }
    
    func testSessionIDHandling() {
        // Test that session IDs are properly handled
        let sessionId = UUID().uuidString
        
        // Create request with specific session ID
        let request = Components.Schemas.ChatRequest(
            message: Components.Schemas.ChatRequest.messagePayload(value1: "Test message"),
            session_id: sessionId
        )
        
        XCTAssertEqual(request.session_id, sessionId)
        
        // Verify session ID format (should be UUID-like)
        let uuidRegex = #"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"#
        let predicate = NSPredicate(format: "SELF MATCHES %@", uuidRegex)
        XCTAssertTrue(predicate.evaluate(with: sessionId))
    }
    
    func testMessageSerialization() throws {
        // Test that messages can be encoded/decoded properly
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()
        
        // Test UserMessage serialization
        let userMessage = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: nil,
            agent_id: "agent-1",
            session_id: "session-1",
            content: "Test content"
        )
        
        let userData = try encoder.encode(userMessage)
        let decodedUser = try decoder.decode(Components.Schemas.UserMessage.self, from: userData)
        
        XCTAssertEqual(decodedUser.agent_id, userMessage.agent_id)
        XCTAssertEqual(decodedUser.session_id, userMessage.session_id)
        XCTAssertEqual(decodedUser.content, userMessage.content)
        
        // Test ChatRequest serialization
        let chatRequest = Components.Schemas.ChatRequest(
            message: Components.Schemas.ChatRequest.messagePayload(value1: "Hello"),
            session_id: "test-123"
        )
        
        let chatData = try encoder.encode(chatRequest)
        let decodedChat = try decoder.decode(Components.Schemas.ChatRequest.self, from: chatData)
        
        XCTAssertEqual(decodedChat.session_id, chatRequest.session_id)
        XCTAssertEqual(decodedChat.message.value1, "Hello")
    }
    
    func testErrorHandling() {
        // Test various error conditions that might occur
        
        // Test empty session ID handling
        let emptySessionRequest = Components.Schemas.ChatRequest(
            message: Components.Schemas.ChatRequest.messagePayload(value1: "Test"),
            session_id: ""
        )
        XCTAssertEqual(emptySessionRequest.session_id, "")
        
        // Test empty message content
        let emptyMessage = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: nil,
            agent_id: "agent",
            session_id: "session",
            content: ""
        )
        XCTAssertEqual(emptyMessage.content, "")
        
        // Test special characters in content
        let specialCharsMessage = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: nil,
            agent_id: "agent",
            session_id: "session",
            content: "Test with special chars: 🎉 <>&\"'\n\t"
        )
        XCTAssertEqual(specialCharsMessage.content, "Test with special chars: 🎉 <>&\"'\n\t")
    }
    
    func testTimestampHandling() {
        // Test timestamp fields
        let timestamp = Date()
        
        let messageWithTimestamp = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: timestamp,
            agent_id: "agent",
            session_id: "session",
            content: "Message with timestamp"
        )
        
        XCTAssertNotNil(messageWithTimestamp.timestamp)
        XCTAssertEqual(messageWithTimestamp.timestamp, timestamp)
        
        // Test message without timestamp
        let messageNoTimestamp = Components.Schemas.UserMessage(
            _type: .user,
            timestamp: nil,
            agent_id: "agent",
            session_id: "session",
            content: "Message without timestamp"
        )
        
        XCTAssertNil(messageNoTimestamp.timestamp)
    }
}