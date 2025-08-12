// Auto-generated error handling - DO NOT EDIT

import Foundation

public enum MetagenAPIError: Error, LocalizedError {
    case networkError(Error)
    case apiError(statusCode: Int, message: String?, body: Data?)
    case decodingError(Error)
    case invalidResponse
    case versionMismatch(expected: String, received: String)
    case streamError(String)
    
    public var errorDescription: String? {
        switch self {
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .apiError(let statusCode, let message, _):
            return "API error \(statusCode): \(message ?? "Unknown error")"
        case .decodingError(let error):
            return "Decoding error: \(error.localizedDescription)"
        case .invalidResponse:
            return "Invalid response from server"
        case .versionMismatch(let expected, let received):
            return "API version mismatch: expected \(expected), received \(received)"
        case .streamError(let message):
            return "Stream error: \(message)"
        }
    }
}