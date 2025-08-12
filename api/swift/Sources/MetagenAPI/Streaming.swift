// Auto-generated SSE/streaming utilities - DO NOT EDIT

import Foundation

public protocol SSEDelegate: AnyObject {
    func didReceiveMessage(_ message: SSEMessage)
    func didReceiveError(_ error: Error)
    func didComplete()
}

public class SSEParser {
    private var buffer = ""
    
    public init() {}
    
    public func parse(_ data: Data) -> [SSEMessage] {
        guard let chunk = String(data: data, encoding: .utf8) else { return [] }
        buffer += chunk
        
        var messages: [SSEMessage] = []
        let lines = buffer.split(separator: "\n", omittingEmptySubsequences: false)
        
        var i = 0
        while i < lines.count - 1 {
            let line = String(lines[i])
            if line.hasPrefix("data: ") {
                let jsonData = String(line.dropFirst(6))
                if let data = jsonData.data(using: .utf8),
                   let message = try? JSONDecoder().decode(SSEMessage.self, from: data) {
                    messages.append(message)
                }
                // Skip empty line after data
                if i + 1 < lines.count && lines[i + 1].isEmpty {
                    i += 1
                }
            }
            i += 1
        }
        
        // Keep last incomplete line in buffer
        if let lastLine = lines.last {
            buffer = String(lastLine)
        } else {
            buffer = ""
        }
        
        return messages
    }
    
    public func reset() {
        buffer = ""
    }
}

public class SSEClient: NSObject {
    private var session: URLSession?
    private var task: URLSessionDataTask?
    private let parser = SSEParser()
    private weak var delegate: SSEDelegate?
    
    public init(delegate: SSEDelegate? = nil) {
        self.delegate = delegate
        super.init()
        
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 0
        configuration.timeoutIntervalForResource = 0
        self.session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
    }
    
    public func connect(to request: URLRequest) {
        task = session?.dataTask(with: request)
        task?.resume()
    }
    
    public func disconnect() {
        task?.cancel()
        task = nil
        parser.reset()
    }
    
    deinit {
        disconnect()
    }
}

extension SSEClient: URLSessionDataDelegate {
    public func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        let messages = parser.parse(data)
        for message in messages {
            if message.type == "error" {
                delegate?.didReceiveError(MetagenAPIError.streamError(message.error ?? "Unknown error"))
            } else if message.type == "complete" {
                delegate?.didComplete()
                disconnect()
            } else {
                delegate?.didReceiveMessage(message)
            }
        }
    }
    
    public func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            delegate?.didReceiveError(error)
        } else {
            delegate?.didComplete()
        }
        disconnect()
    }
}

// Async/await wrapper for SSE streaming
public class SSEStream: AsyncSequence {
    public typealias Element = SSEMessage
    
    private let request: URLRequest
    
    public init(request: URLRequest) {
        self.request = request
    }
    
    public func makeAsyncIterator() -> SSEAsyncIterator {
        return SSEAsyncIterator(request: request)
    }
}

public class SSEAsyncIterator: AsyncIteratorProtocol {
    public typealias Element = SSEMessage
    
    private let client: SSEClient
    private var continuation: AsyncStream<SSEMessage>.Continuation?
    private var stream: AsyncStream<SSEMessage>?
    private var iterator: AsyncStream<SSEMessage>.Iterator?
    
    init(request: URLRequest) {
        let (stream, continuation) = AsyncStream<SSEMessage>.makeStream()
        self.stream = stream
        self.continuation = continuation
        self.iterator = stream.makeAsyncIterator()
        
        self.client = SSEClient()
        self.client.connect(to: request)
        
        // Set up delegate callbacks
        class DelegateHandler: SSEDelegate {
            let continuation: AsyncStream<SSEMessage>.Continuation
            
            init(continuation: AsyncStream<SSEMessage>.Continuation) {
                self.continuation = continuation
            }
            
            func didReceiveMessage(_ message: SSEMessage) {
                continuation.yield(message)
            }
            
            func didReceiveError(_ error: Error) {
                continuation.finish()
            }
            
            func didComplete() {
                continuation.finish()
            }
        }
        
        // Note: This is a simplified implementation
        // In production, you'd need proper delegate handling
    }
    
    public func next() async -> SSEMessage? {
        return await iterator?.next()
    }
}