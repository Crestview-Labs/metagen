/**
 * E2E tests for chat streaming functionality
 * Port of TypeScript tests from api/ts/tests/e2e/chat-stream.test.ts
 */

import XCTest
import Foundation
@testable import MetagenAPI

final class ChatStreamE2ETests: XCTestCase {
    
    var client: MetagenStreamingClient!
    let baseURL = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "http://localhost:8080"
    
    override func setUpWithError() throws {
        super.setUp()
        
        // Initialize streaming client
        client = try MetagenStreamingClient(baseURL: baseURL)
        
        // Verify server is running
        let expectation = self.expectation(description: "Server check")
        
        let url = URL(string: "\(baseURL)/docs")!
        let task = URLSession.shared.dataTask(with: url) { data, response, error in
            if let httpResponse = response as? HTTPURLResponse {
                XCTAssertEqual(httpResponse.statusCode, 200, "Server not responding at \(self.baseURL). Start it with: ./start_server.sh --test")
            } else {
                XCTFail("Server not running on \(self.baseURL)")
            }
            expectation.fulfill()
        }
        task.resume()
        
        wait(for: [expectation], timeout: 5.0)
    }
    
    // MARK: - Helper Functions
    
    func collectStreamMessages(
        message: String,
        sessionId: String,
        maxMessages: Int = 100
    ) async throws -> [[String: Any]] {
        var messages: [[String: Any]] = []
        var count = 0
        
        for try await response in client.chatStream(message: message, sessionId: sessionId) {
            if let dict = response as? [String: Any] {
                messages.append(dict)
                count += 1
                
                // Check for final message
                if let type = dict["type"] as? String,
                   type == "agent",
                   let final = dict["final"] as? Bool,
                   final {
                    break
                }
                
                // Safety limit
                if count >= maxMessages {
                    break
                }
            }
        }
        
        return messages
    }
    
    // MARK: - Basic Tests
    
    func testBasicChatStream() async throws {
        let sessionId = UUID().uuidString
        
        let messages = try await collectStreamMessages(
            message: "Hello, just say hi back",
            sessionId: sessionId
        )
        
        // Verify we got messages
        XCTAssertGreaterThan(messages.count, 0)
        
        // Verify we got agent messages
        let agentMessages = messages.filter { dict in
            if let type = dict["type"] as? String {
                return type == "agent"
            }
            return false
        }
        XCTAssertGreaterThan(agentMessages.count, 0)
        
        // Verify we got a final message
        let finalMessage = agentMessages.first { dict in
            if let final = dict["final"] as? Bool {
                return final
            }
            return false
        }
        XCTAssertNotNil(finalMessage)
    }
    
    func testConcurrentStreams() async throws {
        // Create 3 concurrent sessions
        let sessions = [
            (id: UUID().uuidString, name: "session-1"),
            (id: UUID().uuidString, name: "session-2"),
            (id: UUID().uuidString, name: "session-3")
        ]
        
        // Start all streams concurrently
        let results = try await withThrowingTaskGroup(of: [[String: Any]].self) { group in
            for session in sessions {
                group.addTask {
                    return try await self.collectStreamMessages(
                        message: "Hello from \(session.name)",
                        sessionId: session.id
                    )
                }
            }
            
            var allResults: [[[String: Any]]] = []
            for try await result in group {
                allResults.append(result)
            }
            return allResults
        }
        
        // Verify all completed successfully
        XCTAssertEqual(results.count, 3)
        for messages in results {
            XCTAssertGreaterThan(messages.count, 0)
            
            let agentMessages = messages.filter { dict in
                if let type = dict["type"] as? String {
                    return type == "agent"
                }
                return false
            }
            
            let finalMessage = agentMessages.first { dict in
                if let final = dict["final"] as? Bool {
                    return final
                }
                return false
            }
            XCTAssertNotNil(finalMessage)
        }
    }
    
    func testSessionPersistence() async throws {
        let sessionId = UUID().uuidString
        
        // First request - introduce context
        let messages1 = try await collectStreamMessages(
            message: "My name is Alice and I love Swift programming.",
            sessionId: sessionId
        )
        XCTAssertGreaterThan(messages1.count, 0)
        
        // Second request - test context retention
        let messages2 = try await collectStreamMessages(
            message: "What's my name and what do I love?",
            sessionId: sessionId
        )
        XCTAssertGreaterThan(messages2.count, 0)
        
        // Check that agent remembered the context (basic check)
        let agentResponses = messages2.compactMap { dict -> String? in
            if let type = dict["type"] as? String,
               type == "agent",
               let content = dict["content"] as? String {
                return content
            }
            return nil
        }.joined(separator: " ")
        
        // Agent should have responded with something
        XCTAssertGreaterThan(agentResponses.count, 0)
    }
    
    func testDisconnectionHandling() async throws {
        let sessionId = UUID().uuidString
        
        // Start a request but disconnect early
        var messages1: [[String: Any]] = []
        var count = 0
        
        do {
            for try await response in client.chatStream(
                message: "Start a long explanation about machine learning",
                sessionId: sessionId
            ) {
                if let dict = response as? [String: Any] {
                    messages1.append(dict)
                    count += 1
                    
                    // Simulate early disconnection
                    if count >= 2 {
                        break
                    }
                }
            }
        } catch {
            // Expected - connection might be interrupted
        }
        
        // Wait a bit for server to process disconnection
        try await Task.sleep(nanoseconds: 1_000_000_000) // 1 second
        
        // Reconnect with the same session
        let messages2 = try await collectStreamMessages(
            message: "Are you still there? Just say yes or no.",
            sessionId: sessionId
        )
        XCTAssertGreaterThan(messages2.count, 0)
    }
    
    func testRapidRequests() async throws {
        let sessionId = UUID().uuidString
        let numRequests = 3
        
        // Send multiple requests rapidly with minimal delay
        var requestTasks: [Task<[[String: Any]], Error>] = []
        
        for i in 0..<numRequests {
            // Small stagger to avoid overwhelming the server
            try await Task.sleep(nanoseconds: 100_000_000) // 0.1 seconds
            
            let task = Task {
                try await self.collectStreamMessages(
                    message: "Request \(i): Acknowledge with the number \(i)",
                    sessionId: sessionId
                )
            }
            requestTasks.append(task)
        }
        
        // Wait for all requests to complete
        var results: [[[String: Any]]] = []
        for task in requestTasks {
            let messages = try await task.value
            results.append(messages)
        }
        
        // Verify all requests completed successfully
        XCTAssertEqual(results.count, numRequests)
        
        for messages in results {
            XCTAssertGreaterThan(messages.count, 0)
        }
    }
}