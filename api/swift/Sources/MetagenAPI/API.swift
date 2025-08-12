// Auto-generated API client - DO NOT EDIT

import Foundation

public class MetagenAPI {
    private let baseURL: String
    private let session: URLSession
    
    public init(baseURL: String = "http://localhost:8000") {
        self.baseURL = baseURL
        self.session = URLSession.shared
    }
    
    // MARK: - Chat Endpoints
    
    public func chat(_ request: ChatRequest) async throws -> ChatResponse {
        let response: ChatResponse = try await performRequest(
            path: "/api/chat",
            method: "POST",
            body: request
        )
        return response
    }
    
    public func chatStream(_ request: ChatRequest) -> SSEStream {
        let url = URL(string: "\(baseURL)/api/chat/stream")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        urlRequest.setValue(APIVersion.version, forHTTPHeaderField: "X-API-Version")
        
        if let body = try? JSONEncoder().encode(request) {
            urlRequest.httpBody = body
        }
        
        return SSEStream(request: urlRequest)
    }
    
    public func submitToolDecision(_ decision: ToolDecisionRequest) async throws -> ToolDecisionResponse {
        let response: ToolDecisionResponse = try await performRequest(
            path: "/api/tool-decision",
            method: "POST",
            body: decision
        )
        return response
    }
    
    public func getPendingTools() async throws -> PendingToolsResponse {
        let response: PendingToolsResponse = try await performRequest(
            path: "/api/pending-tools",
            method: "GET"
        )
        return response
    }
    
    // MARK: - Auth Endpoints
    
    public func getAuthStatus() async throws -> AuthStatus {
        let response: AuthStatus = try await performRequest(
            path: "/api/auth/status",
            method: "GET"
        )
        return response
    }
    
    public func login(_ request: AuthLoginRequest = AuthLoginRequest()) async throws -> AuthResponse {
        let response: AuthResponse = try await performRequest(
            path: "/api/auth/login",
            method: "POST",
            body: request
        )
        return response
    }
    
    public func logout() async throws -> AuthResponse {
        let response: AuthResponse = try await performRequest(
            path: "/api/auth/logout",
            method: "POST"
        )
        return response
    }
    
    // MARK: - System Endpoints
    
    public func getSystemInfo() async throws -> SystemInfo {
        let response: SystemInfo = try await performRequest(
            path: "/api/system/info",
            method: "GET"
        )
        return response
    }
    
    public func getHealthCheck() async throws -> HealthCheckResponse {
        let response: HealthCheckResponse = try await performRequest(
            path: "/api/system/health",
            method: "GET"
        )
        return response
    }
    
    // MARK: - Tools Endpoints
    
    public func getTools() async throws -> ToolsResponse {
        let response: ToolsResponse = try await performRequest(
            path: "/api/tools",
            method: "GET"
        )
        return response
    }
    
    public func getGoogleTools() async throws -> GoogleToolsResponse {
        let response: GoogleToolsResponse = try await performRequest(
            path: "/api/tools/google",
            method: "GET"
        )
        return response
    }
    
    // MARK: - Memory Endpoints
    
    public func clearMemory() async throws -> ClearMemoryResponse {
        let response: ClearMemoryResponse = try await performRequest(
            path: "/api/memory/clear",
            method: "POST"
        )
        return response
    }
    
    // MARK: - Telemetry Endpoints
    
    public func getRecentTraces(limit: Int = 20) async throws -> [String] {
        let response: [String] = try await performRequest(
            path: "/api/telemetry/traces?limit=\(limit)",
            method: "GET"
        )
        return response
    }
    
    public func getTrace(traceId: String) async throws -> [String: Any] {
        let response: [String: Any] = try await performRequest(
            path: "/api/telemetry/traces/\(traceId)",
            method: "GET"
        )
        return response
    }
    
    public func analyzeTrace(traceId: String) async throws -> [String: Any] {
        let response: [String: Any] = try await performRequest(
            path: "/api/telemetry/traces/\(traceId)/analysis",
            method: "GET"
        )
        return response
    }
    
    public func getTraceInsights(traceId: String) async throws -> [String: Any] {
        let response: [String: Any] = try await performRequest(
            path: "/api/telemetry/traces/\(traceId)/insights",
            method: "GET"
        )
        return response
    }
    
    public func getTraceReport(traceId: String) async throws -> [String: String] {
        let response: [String: String] = try await performRequest(
            path: "/api/telemetry/traces/\(traceId)/report",
            method: "GET"
        )
        return response
    }
    
    public func getCurrentTrace() async throws -> [String: Any] {
        let response: [String: Any] = try await performRequest(
            path: "/api/telemetry/debug/current",
            method: "GET"
        )
        return response
    }
    
    public func getMemoryTraces(limit: Int = 10) async throws -> [String] {
        let response: [String] = try await performRequest(
            path: "/api/telemetry/memory/traces?limit=\(limit)",
            method: "GET"
        )
        return response
    }
    
    public func getMemoryTrace(traceId: String) async throws -> [String: Any] {
        let response: [String: Any] = try await performRequest(
            path: "/api/telemetry/memory/traces/\(traceId)",
            method: "GET"
        )
        return response
    }
    
    public func getLatestTraceInsights() async throws -> [String: Any] {
        let response: [String: Any] = try await performRequest(
            path: "/api/telemetry/latest/insights",
            method: "GET"
        )
        return response
    }
    
    public func getLatestTraceReport() async throws -> [String: String] {
        let response: [String: String] = try await performRequest(
            path: "/api/telemetry/latest/report",
            method: "GET"
        )
        return response
    }
    
    // MARK: - Private Methods
    
    private func performRequest<T: Decodable>(
        path: String,
        method: String,
        body: Encodable? = nil
    ) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw MetagenAPIError.invalidResponse
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(APIVersion.version, forHTTPHeaderField: "X-API-Version")
        
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }
        
        do {
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MetagenAPIError.invalidResponse
            }
            
            // Check version header
            if let responseVersion = httpResponse.value(forHTTPHeaderField: "X-API-Version"),
               responseVersion != APIVersion.version {
                print("Warning: API version mismatch - expected \(APIVersion.version), received \(responseVersion)")
            }
            
            if httpResponse.statusCode >= 200 && httpResponse.statusCode < 300 {
                do {
                    let decoded = try JSONDecoder().decode(T.self, from: data)
                    return decoded
                } catch {
                    throw MetagenAPIError.decodingError(error)
                }
            } else {
                let message = String(data: data, encoding: .utf8)
                throw MetagenAPIError.apiError(
                    statusCode: httpResponse.statusCode,
                    message: message,
                    body: data
                )
            }
        } catch let error as MetagenAPIError {
            throw error
        } catch {
            throw MetagenAPIError.networkError(error)
        }
    }
    
    // Special handling for [String: Any] responses
    private func performRequest(
        path: String,
        method: String,
        body: Encodable? = nil
    ) async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw MetagenAPIError.invalidResponse
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(APIVersion.version, forHTTPHeaderField: "X-API-Version")
        
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }
        
        do {
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MetagenAPIError.invalidResponse
            }
            
            if httpResponse.statusCode >= 200 && httpResponse.statusCode < 300 {
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                    throw MetagenAPIError.decodingError(NSError(domain: "JSON", code: 0))
                }
                return json
            } else {
                let message = String(data: data, encoding: .utf8)
                throw MetagenAPIError.apiError(
                    statusCode: httpResponse.statusCode,
                    message: message,
                    body: data
                )
            }
        } catch let error as MetagenAPIError {
            throw error
        } catch {
            throw MetagenAPIError.networkError(error)
        }
    }
    
    // Special handling for [String] responses
    private func performRequest(
        path: String,
        method: String,
        body: Encodable? = nil
    ) async throws -> [String] {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw MetagenAPIError.invalidResponse
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(APIVersion.version, forHTTPHeaderField: "X-API-Version")
        
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }
        
        do {
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MetagenAPIError.invalidResponse
            }
            
            if httpResponse.statusCode >= 200 && httpResponse.statusCode < 300 {
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String] else {
                    throw MetagenAPIError.decodingError(NSError(domain: "JSON", code: 0))
                }
                return json
            } else {
                let message = String(data: data, encoding: .utf8)
                throw MetagenAPIError.apiError(
                    statusCode: httpResponse.statusCode,
                    message: message,
                    body: data
                )
            }
        } catch let error as MetagenAPIError {
            throw error
        } catch {
            throw MetagenAPIError.networkError(error)
        }
    }
    
    // Special handling for [String: String] responses
    private func performRequest(
        path: String,
        method: String,
        body: Encodable? = nil
    ) async throws -> [String: String] {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw MetagenAPIError.invalidResponse
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(APIVersion.version, forHTTPHeaderField: "X-API-Version")
        
        if let body = body {
            request.httpBody = try JSONEncoder().encode(body)
        }
        
        do {
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw MetagenAPIError.invalidResponse
            }
            
            if httpResponse.statusCode >= 200 && httpResponse.statusCode < 300 {
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String: String] else {
                    throw MetagenAPIError.decodingError(NSError(domain: "JSON", code: 0))
                }
                return json
            } else {
                let message = String(data: data, encoding: .utf8)
                throw MetagenAPIError.apiError(
                    statusCode: httpResponse.statusCode,
                    message: message,
                    body: data
                )
            }
        } catch let error as MetagenAPIError {
            throw error
        } catch {
            throw MetagenAPIError.networkError(error)
        }
    }
}

// MARK: - Shared Instance

public extension MetagenAPI {
    static let shared = MetagenAPI()
}