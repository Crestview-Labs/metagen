// Auto-generated from api/models - DO NOT EDIT

import Foundation

// MARK: - Chat Models (from api/models/chat.py)

public struct ChatRequest: Codable {
    public let message: String
    public let sessionId: String?
    
    public init(message: String, sessionId: String? = nil) {
        self.message = message
        self.sessionId = sessionId
    }
    
    enum CodingKeys: String, CodingKey {
        case message
        case sessionId = "session_id"
    }
}

public struct UIResponseModel: Codable {
    public let type: String
    public let content: String
    public let agentId: String
    public let metadata: [String: Any]?
    public let timestamp: String
    
    enum CodingKeys: String, CodingKey {
        case type
        case content
        case agentId = "agent_id"
        case metadata
        case timestamp
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        content = try container.decode(String.self, forKey: .content)
        agentId = try container.decode(String.self, forKey: .agentId)
        timestamp = try container.decode(String.self, forKey: .timestamp)
        
        if let metadataData = try? container.decode([String: Any].self, forKey: .metadata) {
            metadata = metadataData
        } else {
            metadata = nil
        }
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encode(content, forKey: .content)
        try container.encode(agentId, forKey: .agentId)
        try container.encode(timestamp, forKey: .timestamp)
        if let metadata = metadata {
            try container.encode(metadata, forKey: .metadata)
        }
    }
}

public struct ChatResponse: Codable {
    public let responses: [UIResponseModel]
    public let sessionId: String?
    public let success: Bool
    
    enum CodingKeys: String, CodingKey {
        case responses
        case sessionId = "session_id"
        case success
    }
}

// MARK: - Auth Models (from api/models/auth.py)

public struct AuthStatus: Codable {
    public let authenticated: Bool
    public let userInfo: [String: String]?
    public let services: [String]
    public let provider: String?
    
    enum CodingKeys: String, CodingKey {
        case authenticated
        case userInfo = "user_info"
        case services
        case provider
    }
}

public struct AuthLoginRequest: Codable {
    public let force: Bool?
    
    public init(force: Bool? = false) {
        self.force = force
    }
}

public struct AuthResponse: Codable {
    public let success: Bool
    public let message: String
    public let authUrl: String?
    public let status: AuthStatus?
    
    enum CodingKeys: String, CodingKey {
        case success
        case message
        case authUrl = "auth_url"
        case status
    }
}

// MARK: - System Models (from api/models/system.py)

public struct ToolInfo: Codable {
    public let name: String
    public let description: String
    public let inputSchema: [String: Any]
    
    enum CodingKeys: String, CodingKey {
        case name
        case description
        case inputSchema = "input_schema"
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        description = try container.decode(String.self, forKey: .description)
        inputSchema = try container.decode([String: Any].self, forKey: .inputSchema)
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(description, forKey: .description)
        try container.encode(inputSchema, forKey: .inputSchema)
    }
}

public struct ToolsResponse: Codable {
    public let tools: [ToolInfo]
    public let count: Int
}

public struct SystemInfo: Codable {
    public let agentName: String
    public let model: String
    public let tools: [ToolInfo]
    public let toolCount: Int
    public let memoryPath: String
    public let initialized: Bool
    
    enum CodingKeys: String, CodingKey {
        case agentName = "agent_name"
        case model
        case tools
        case toolCount = "tool_count"
        case memoryPath = "memory_path"
        case initialized
    }
}

// MARK: - Common Models (from api/models/common.py)

public struct ErrorResponse: Codable {
    public let error: String
    public let errorType: String?
    public let timestamp: String
    
    enum CodingKeys: String, CodingKey {
        case error
        case errorType = "error_type"
        case timestamp
    }
}

public struct SuccessResponse: Codable {
    public let message: String
    public let data: [String: Any]?
    public let timestamp: String
    
    enum CodingKeys: String, CodingKey {
        case message
        case data
        case timestamp
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        message = try container.decode(String.self, forKey: .message)
        timestamp = try container.decode(String.self, forKey: .timestamp)
        data = try? container.decode([String: Any].self, forKey: .data)
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(message, forKey: .message)
        try container.encode(timestamp, forKey: .timestamp)
        if let data = data {
            try container.encode(data, forKey: .data)
        }
    }
}

// MARK: - Additional Route Models

public struct ToolDecisionRequest: Codable {
    public let toolId: String
    public let decision: String
    public let feedback: String?
    public let agentId: String?
    
    public init(toolId: String, decision: String, feedback: String? = nil, agentId: String? = nil) {
        self.toolId = toolId
        self.decision = decision
        self.feedback = feedback
        self.agentId = agentId
    }
    
    enum CodingKeys: String, CodingKey {
        case toolId = "tool_id"
        case decision
        case feedback
        case agentId = "agent_id"
    }
}

public struct ToolDecisionResponse: Codable {
    public let success: Bool
    public let toolId: String
    public let decision: String
    
    enum CodingKeys: String, CodingKey {
        case success
        case toolId = "tool_id"
        case decision
    }
}

public struct PendingTool: Codable {
    public let toolId: String
    public let toolName: String
    public let toolArgs: [String: Any]
    public let agentId: String
    public let createdAt: String?
    public let requiresApproval: Bool
    
    enum CodingKeys: String, CodingKey {
        case toolId = "tool_id"
        case toolName = "tool_name"
        case toolArgs = "tool_args"
        case agentId = "agent_id"
        case createdAt = "created_at"
        case requiresApproval = "requires_approval"
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        toolId = try container.decode(String.self, forKey: .toolId)
        toolName = try container.decode(String.self, forKey: .toolName)
        toolArgs = try container.decode([String: Any].self, forKey: .toolArgs)
        agentId = try container.decode(String.self, forKey: .agentId)
        createdAt = try? container.decode(String.self, forKey: .createdAt)
        requiresApproval = try container.decode(Bool.self, forKey: .requiresApproval)
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(toolId, forKey: .toolId)
        try container.encode(toolName, forKey: .toolName)
        try container.encode(toolArgs, forKey: .toolArgs)
        try container.encode(agentId, forKey: .agentId)
        try container.encodeIfPresent(createdAt, forKey: .createdAt)
        try container.encode(requiresApproval, forKey: .requiresApproval)
    }
}

public struct PendingToolsResponse: Codable {
    public let success: Bool
    public let pendingTools: [PendingTool]
    public let count: Int
    
    enum CodingKeys: String, CodingKey {
        case success
        case pendingTools = "pending_tools"
        case count
    }
}

public struct HealthCheckResponse: Codable {
    public let status: String
    public let components: Components?
    public let error: String?
    public let timestamp: String
    
    public struct Components: Codable {
        public let manager: String
        public let agent: String
        public let tools: String
    }
}

public struct GoogleToolsResponse: Codable {
    public let count: Int
    public let tools: [[String: Any]]
    public let services: Services
    
    public struct Services: Codable {
        public let gmail: [[String: Any]]
        public let drive: [[String: Any]]
        public let calendar: [[String: Any]]
        
        public init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            gmail = try container.decode([[String: Any]].self, forKey: .gmail)
            drive = try container.decode([[String: Any]].self, forKey: .drive)
            calendar = try container.decode([[String: Any]].self, forKey: .calendar)
        }
        
        public func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(gmail, forKey: .gmail)
            try container.encode(drive, forKey: .drive)
            try container.encode(calendar, forKey: .calendar)
        }
        
        enum CodingKeys: String, CodingKey {
            case gmail, drive, calendar
        }
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        count = try container.decode(Int.self, forKey: .count)
        tools = try container.decode([[String: Any]].self, forKey: .tools)
        services = try container.decode(Services.self, forKey: .services)
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(count, forKey: .count)
        try container.encode(tools, forKey: .tools)
        try container.encode(services, forKey: .services)
    }
    
    enum CodingKeys: String, CodingKey {
        case count, tools, services
    }
}

public struct ClearMemoryResponse: Codable {
    public let message: String
    public let conversationTurnsDeleted: String
    public let telemetrySpansDeleted: String
    
    enum CodingKeys: String, CodingKey {
        case message
        case conversationTurnsDeleted = "conversation_turns_deleted"
        case telemetrySpansDeleted = "telemetry_spans_deleted"
    }
}

// MARK: - SSE Models

public struct SSEMessage: Codable {
    public let type: String
    public let content: String?
    public let agentId: String?
    public let metadata: [String: Any]?
    public let timestamp: String?
    public let sessionId: String?
    public let error: String?
    
    enum CodingKeys: String, CodingKey {
        case type
        case content
        case agentId = "agent_id"
        case metadata
        case timestamp
        case sessionId = "session_id"
        case error
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        content = try? container.decode(String.self, forKey: .content)
        agentId = try? container.decode(String.self, forKey: .agentId)
        metadata = try? container.decode([String: Any].self, forKey: .metadata)
        timestamp = try? container.decode(String.self, forKey: .timestamp)
        sessionId = try? container.decode(String.self, forKey: .sessionId)
        error = try? container.decode(String.self, forKey: .error)
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encodeIfPresent(content, forKey: .content)
        try container.encodeIfPresent(agentId, forKey: .agentId)
        if let metadata = metadata {
            try container.encode(metadata, forKey: .metadata)
        }
        try container.encodeIfPresent(timestamp, forKey: .timestamp)
        try container.encodeIfPresent(sessionId, forKey: .sessionId)
        try container.encodeIfPresent(error, forKey: .error)
    }
}

// MARK: - Helpers for [String: Any] encoding/decoding

extension KeyedDecodingContainer {
    public func decode(_ type: [String: Any].Type, forKey key: K) throws -> [String: Any] {
        let container = try self.nestedContainer(keyedBy: JSONCodingKey.self, forKey: key)
        return try container.decode(type)
    }
    
    public func decode(_ type: [[String: Any]].Type, forKey key: K) throws -> [[String: Any]] {
        var container = try self.nestedUnkeyedContainer(forKey: key)
        return try container.decode(type)
    }
}

extension KeyedEncodingContainer {
    public mutating func encode(_ value: [String: Any], forKey key: K) throws {
        var container = self.nestedContainer(keyedBy: JSONCodingKey.self, forKey: key)
        try container.encode(value)
    }
    
    public mutating func encode(_ value: [[String: Any]], forKey key: K) throws {
        var container = self.nestedUnkeyedContainer(forKey: key)
        try container.encode(value)
    }
}

extension UnkeyedDecodingContainer {
    mutating func decode(_ type: [[String: Any]].Type) throws -> [[String: Any]] {
        var array: [[String: Any]] = []
        while !isAtEnd {
            if let value = try? decode([String: Any].self) {
                array.append(value)
            } else {
                // Skip non-dict values by decoding as a dummy value
                _ = try? decodeNil()
                if !isAtEnd {
                    _ = try? decode(String.self)
                }
            }
        }
        return array
    }
    
    mutating func decode(_ type: [String: Any].Type) throws -> [String: Any] {
        let container = try self.nestedContainer(keyedBy: JSONCodingKey.self)
        return try container.decode(type)
    }
}

extension UnkeyedEncodingContainer {
    mutating func encode(_ value: [[String: Any]]) throws {
        for dict in value {
            try encode(dict)
        }
    }
    
    mutating func encode(_ value: [String: Any]) throws {
        var container = self.nestedContainer(keyedBy: JSONCodingKey.self)
        try container.encode(value)
    }
}

private extension KeyedDecodingContainer where K == JSONCodingKey {
    func decode(_ type: [String: Any].Type) throws -> [String: Any] {
        var dictionary: [String: Any] = [:]
        for key in allKeys {
            if let value = try? decode(Bool.self, forKey: key) {
                dictionary[key.stringValue] = value
            } else if let value = try? decode(Int.self, forKey: key) {
                dictionary[key.stringValue] = value
            } else if let value = try? decode(Double.self, forKey: key) {
                dictionary[key.stringValue] = value
            } else if let value = try? decode(String.self, forKey: key) {
                dictionary[key.stringValue] = value
            } else if let value = try? decode([String: Any].self, forKey: key) {
                dictionary[key.stringValue] = value
            } else if let value = try? decode([[String: Any]].self, forKey: key) {
                dictionary[key.stringValue] = value
            }
        }
        return dictionary
    }
}

private extension KeyedEncodingContainer where K == JSONCodingKey {
    mutating func encode(_ value: [String: Any]) throws {
        for (key, val) in value {
            let key = JSONCodingKey(stringValue: key)
            switch val {
            case let v as Bool:
                try encode(v, forKey: key)
            case let v as Int:
                try encode(v, forKey: key)
            case let v as Double:
                try encode(v, forKey: key)
            case let v as String:
                try encode(v, forKey: key)
            case let v as [String: Any]:
                try encode(v, forKey: key)
            case let v as [[String: Any]]:
                try encode(v, forKey: key)
            default:
                // Skip values we can't encode
                continue
            }
        }
    }
}

private struct JSONCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?
    
    init(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }
    
    init(intValue: Int) {
        self.stringValue = "\(intValue)"
        self.intValue = intValue
    }
}