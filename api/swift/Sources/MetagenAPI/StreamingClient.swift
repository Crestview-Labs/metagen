// SSE Streaming wrapper for Metagen API v0.1.1
// Generated: 2025-08-28T18:53:55.532997+00:00

import Foundation
import OpenAPIRuntime
import OpenAPIURLSession

/// SSE Streaming wrapper for Metagen API
public class MetagenStreamingClient {
    private let client: Client
    private let baseURL: URL
    
    public init(baseURL: String = "http://localhost:8080") throws {
        self.baseURL = URL(string: baseURL)!
        self.client = Client(
            serverURL: self.baseURL,
            transport: URLSessionTransport()
        )
    }
    
    /// Stream chat responses using Server-Sent Events
    public func chatStream(
        message: String,
        sessionId: String
    ) -> AsyncThrowingStream<Any, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    let url = baseURL.appendingPathComponent("/api/chat/stream")
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    
                    let body = ["message": message, "session_id": sessionId]
                    request.httpBody = try JSONSerialization.data(withJSONObject: body)
                    
                    let (bytes, _) = try await URLSession.shared.bytes(for: request)
                    
                    for try await line in bytes.lines {
                        if line.hasPrefix("data: ") {
                            let jsonStr = String(line.dropFirst(6))
                            if let data = jsonStr.data(using: .utf8) {
                                let response = try JSONSerialization.jsonObject(with: data)
                                continuation.yield(response)
                                
                                // Check for completion
                                if let dict = response as? [String: Any] {
                                    // Check if it's an agent message with final flag
                                    if let type = dict["type"] as? String, 
                                       type == "agent",
                                       let final = dict["final"] as? Bool,
                                       final == true {
                                        continuation.finish()
                                        return
                                    }
                                    // Also check for explicit complete type (legacy)
                                    if let type = dict["type"] as? String,
                                       type == "complete" {
                                        continuation.finish()
                                        return
                                    }
                                }
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
