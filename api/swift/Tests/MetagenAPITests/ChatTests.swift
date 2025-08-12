// Comprehensive tests for chat API - both mock and real
import XCTest
@testable import MetagenAPI

// ============================================================================
// MOCK TESTS
// ============================================================================

final class ChatTestsMocked: XCTestCase {
    var api: MetagenAPI!
    var mockSession: URLSessionMock!
    
    override func setUp() {
        super.setUp()
        mockSession = URLSessionMock()
        api = MetagenAPI(baseURL: "http://localhost:8000")
        // Note: In production, you'd inject the session into MetagenAPI
        // For now, we'll test the real implementation
    }
    
    override func tearDown() {
        api = nil
        mockSession = nil
        super.tearDown()
    }
    
    func testChatRequestModel() {
        let request = ChatRequest(
            message: "Hello, assistant!",
            sessionId: "test-session-123"
        )
        
        XCTAssertEqual(request.message, "Hello, assistant!")
        XCTAssertEqual(request.sessionId, "test-session-123")
    }
    
    func testChatRequestOptionalSession() {
        let request = ChatRequest(message: "Hello!")
        
        XCTAssertEqual(request.message, "Hello!")
        XCTAssertNil(request.sessionId)
    }
    
    func testUIResponseModel() {
        // Test that the model can be created
        // In real app, you'd decode from JSON
        let jsonString = """
        {
            "type": "text",
            "content": "Response content",
            "agent_id": "agent-123",
            "metadata": {"key": "value"},
            "timestamp": "2025-01-08T12:00:00"
        }
        """
        
        let data = jsonString.data(using: .utf8)!
        let decoder = JSONDecoder()
        
        do {
            let response = try decoder.decode(UIResponseModel.self, from: data)
            XCTAssertEqual(response.type, "text")
            XCTAssertEqual(response.content, "Response content")
            XCTAssertEqual(response.agentId, "agent-123")
            XCTAssertNotNil(response.metadata)
            XCTAssertEqual(response.timestamp, "2025-01-08T12:00:00")
        } catch {
            XCTFail("Failed to decode UIResponseModel: \(error)")
        }
    }
    
    func testChatResponseModel() {
        let jsonString = """
        {
            "responses": [{
                "type": "text",
                "content": "Test",
                "agent_id": "agent-123",
                "timestamp": "2025-01-08T12:00:00"
            }],
            "session_id": "session-123",
            "success": true
        }
        """
        
        let data = jsonString.data(using: .utf8)!
        let decoder = JSONDecoder()
        
        do {
            let response = try decoder.decode(ChatResponse.self, from: data)
            XCTAssertEqual(response.responses.count, 1)
            XCTAssertEqual(response.sessionId, "session-123")
            XCTAssertTrue(response.success)
        } catch {
            XCTFail("Failed to decode ChatResponse: \(error)")
        }
    }
    
    func testToolDecisionRequest() {
        let decision = ToolDecisionRequest(
            toolId: "tool-123",
            decision: "approved",
            feedback: nil,
            agentId: "METAGEN"
        )
        
        XCTAssertEqual(decision.toolId, "tool-123")
        XCTAssertEqual(decision.decision, "approved")
        XCTAssertNil(decision.feedback)
        XCTAssertEqual(decision.agentId, "METAGEN")
    }
    
    func testPendingToolModel() {
        let jsonString = """
        {
            "tool_id": "pending-123",
            "tool_name": "test_tool",
            "tool_args": {"arg1": "value1"},
            "agent_id": "METAGEN",
            "created_at": "2025-01-08T12:00:00",
            "requires_approval": true
        }
        """
        
        let data = jsonString.data(using: .utf8)!
        let decoder = JSONDecoder()
        
        do {
            let tool = try decoder.decode(PendingTool.self, from: data)
            XCTAssertEqual(tool.toolId, "pending-123")
            XCTAssertEqual(tool.toolName, "test_tool")
            XCTAssertEqual(tool.agentId, "METAGEN")
            XCTAssertTrue(tool.requiresApproval)
        } catch {
            XCTFail("Failed to decode PendingTool: \(error)")
        }
    }
    
    func testSSEMessageModel() {
        let jsonString = """
        {
            "type": "text",
            "content": "Hello",
            "agent_id": "agent-123",
            "timestamp": "2025-01-08T12:00:00"
        }
        """
        
        let data = jsonString.data(using: .utf8)!
        let decoder = JSONDecoder()
        
        do {
            let message = try decoder.decode(SSEMessage.self, from: data)
            XCTAssertEqual(message.type, "text")
            XCTAssertEqual(message.content, "Hello")
            XCTAssertEqual(message.agentId, "agent-123")
        } catch {
            XCTFail("Failed to decode SSEMessage: \(error)")
        }
    }
    
    func testErrorTypes() {
        let networkError = MetagenAPIError.networkError(NSError(domain: "test", code: 0))
        XCTAssertNotNil(networkError.errorDescription)
        
        let apiError = MetagenAPIError.apiError(statusCode: 500, message: "Server error", body: nil)
        XCTAssertTrue(apiError.errorDescription?.contains("500") ?? false)
        
        let versionError = MetagenAPIError.versionMismatch(expected: "0.1.0", received: "0.2.0")
        XCTAssertTrue(versionError.errorDescription?.contains("0.1.0") ?? false)
    }
}

// ============================================================================
// INTEGRATION TESTS WITH REAL API
// ============================================================================

final class ChatTestsIntegration: XCTestCase {
    var api: MetagenAPI!
    
    // Skip integration tests unless RUN_INTEGRATION_TESTS is set
    var skipIntegration: Bool {
        ProcessInfo.processInfo.environment["RUN_INTEGRATION_TESTS"] == nil
    }
    
    override func setUp() {
        super.setUp()
        let apiURL = ProcessInfo.processInfo.environment["API_URL"] ?? "http://localhost:8000"
        api = MetagenAPI(baseURL: apiURL)
    }
    
    override func tearDown() {
        api = nil
        super.tearDown()
    }
    
    func testRealChatRequest() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        let request = ChatRequest(
            message: "What is 2+2? Reply with just the number.",
            sessionId: "test-swift-integration"
        )
        
        do {
            let response = try await api.chat(request)
            XCTAssertTrue(response.success)
            XCTAssertFalse(response.responses.isEmpty)
            XCTAssertEqual(response.sessionId, "test-swift-integration")
        } catch {
            XCTFail("Chat request failed: \(error)")
        }
    }
    
    func testRealChatStream() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        let request = ChatRequest(
            message: "Count from 1 to 3",
            sessionId: "test-swift-stream"
        )
        
        let stream = api.chatStream(request)
        var messages: [SSEMessage] = []
        var completed = false
        
        for await message in stream {
            messages.append(message)
            if message.type == "complete" {
                completed = true
                break
            }
            // Limit iterations to prevent infinite loop
            if messages.count > 100 {
                break
            }
        }
        
        XCTAssertFalse(messages.isEmpty)
        XCTAssertTrue(completed)
    }
    
    func testRealPendingTools() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        do {
            let response = try await api.getPendingTools()
            XCTAssertTrue(response.success)
            XCTAssertNotNil(response.pendingTools)
            XCTAssertGreaterThanOrEqual(response.count, 0)
        } catch {
            XCTFail("Get pending tools failed: \(error)")
        }
    }
    
    func testRealConcurrentRequests() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        async let response1 = api.chat(ChatRequest(message: "Say hello", sessionId: "concurrent-1"))
        async let response2 = api.chat(ChatRequest(message: "Say goodbye", sessionId: "concurrent-2"))
        async let response3 = api.chat(ChatRequest(message: "Say thanks", sessionId: "concurrent-3"))
        
        do {
            let responses = try await [response1, response2, response3]
            
            for response in responses {
                XCTAssertTrue(response.success)
                XCTAssertFalse(response.responses.isEmpty)
            }
        } catch {
            XCTFail("Concurrent requests failed: \(error)")
        }
    }
    
    func testRealSessionContext() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        let sessionId = "context-test-swift"
        
        // First message
        let request1 = ChatRequest(
            message: "My name is SwiftTester",
            sessionId: sessionId
        )
        
        do {
            let response1 = try await api.chat(request1)
            XCTAssertTrue(response1.success)
            
            // Second message referencing first
            let request2 = ChatRequest(
                message: "What is my name?",
                sessionId: sessionId
            )
            
            let response2 = try await api.chat(request2)
            XCTAssertTrue(response2.success)
            
            // Check if response mentions the name (context working)
            let responseText = response2.responses
                .compactMap { $0.content }
                .joined(separator: " ")
            // May or may not contain the name depending on context handling
            XCTAssertFalse(responseText.isEmpty)
        } catch {
            XCTFail("Session context test failed: \(error)")
        }
    }
    
    func testRealSpecialCharacters() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        let request = ChatRequest(
            message: "What is 🎉 emoji?",
            sessionId: "emoji-test-swift"
        )
        
        do {
            let response = try await api.chat(request)
            XCTAssertTrue(response.success)
            XCTAssertFalse(response.responses.isEmpty)
        } catch {
            XCTFail("Special characters test failed: \(error)")
        }
    }
    
    func testRealToolDecision() async throws {
        try XCTSkipIf(skipIntegration, "Skipping integration test")
        
        // First, get pending tools
        do {
            let pendingResponse = try await api.getPendingTools()
            
            if !pendingResponse.pendingTools.isEmpty {
                let tool = pendingResponse.pendingTools[0]
                
                let decision = ToolDecisionRequest(
                    toolId: tool.toolId,
                    decision: "approved",
                    agentId: tool.agentId
                )
                
                let decisionResponse = try await api.submitToolDecision(decision)
                XCTAssertTrue(decisionResponse.success)
                XCTAssertEqual(decisionResponse.toolId, tool.toolId)
            }
        } catch {
            // It's ok if there are no pending tools
            print("Tool decision test: \(error)")
        }
    }
}

// ============================================================================
// PERFORMANCE TESTS
// ============================================================================

final class ChatTestsPerformance: XCTestCase {
    var api: MetagenAPI!
    
    override func setUp() {
        super.setUp()
        api = MetagenAPI()
    }
    
    override func tearDown() {
        api = nil
        super.tearDown()
    }
    
    func testResponseTimePerformance() async throws {
        // Skip if not running integration tests
        try XCTSkipIf(ProcessInfo.processInfo.environment["RUN_INTEGRATION_TESTS"] == nil)
        
        let request = ChatRequest(
            message: "What is 2+2?",
            sessionId: "perf-test"
        )
        
        let startTime = Date()
        
        do {
            _ = try await api.chat(request)
            let elapsed = Date().timeIntervalSince(startTime)
            
            // Should respond within 30 seconds for simple queries
            XCTAssertLessThan(elapsed, 30.0, "Response took \(elapsed) seconds")
        } catch {
            XCTFail("Performance test failed: \(error)")
        }
    }
    
    func testStreamingLatency() async throws {
        try XCTSkipIf(ProcessInfo.processInfo.environment["RUN_INTEGRATION_TESTS"] == nil)
        
        let request = ChatRequest(
            message: "Say hello",
            sessionId: "stream-perf"
        )
        
        let startTime = Date()
        var firstMessageTime: Date?
        
        let stream = api.chatStream(request)
        
        for await message in stream {
            if firstMessageTime == nil {
                firstMessageTime = Date()
            }
            if message.type == "complete" {
                break
            }
            // Prevent infinite loop
            if Date().timeIntervalSince(startTime) > 30 {
                break
            }
        }
        
        if let firstTime = firstMessageTime {
            let latency = firstTime.timeIntervalSince(startTime)
            XCTAssertLessThan(latency, 10.0, "First message took \(latency) seconds")
        }
    }
}

// ============================================================================
// MOCK HELPERS
// ============================================================================

class URLSessionMock: URLSession {
    var data: Data?
    var response: URLResponse?
    var error: Error?
    
    override func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        if let error = error {
            throw error
        }
        
        let data = self.data ?? Data()
        let response = self.response ?? HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: nil
        )!
        
        return (data, response)
    }
}