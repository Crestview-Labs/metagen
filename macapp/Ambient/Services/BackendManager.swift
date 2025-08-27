import Foundation
import Combine

@MainActor
class BackendManager: ObservableObject {
    @Published var status: BackendStatus = .stopped
    @Published var port: Int = 8080
    @Published var error: String?
    
    private var process: Process?
    private var checkTimer: Timer?
    
    enum BackendStatus {
        case stopped
        case starting
        case running
        case error(String)
        
        var isRunning: Bool {
            if case .running = self { return true }
            return false
        }
    }
    
    func start() {
        guard !status.isRunning else { return }
        
        status = .starting
        
        Task {
            do {
                // Check if backend is already running
                if await checkHealth() {
                    status = .running
                    return
                }
                
                // Start backend process
                try await startBackendProcess()
                
                // Wait for backend to be ready
                try await waitForBackend()
                
                status = .running
                startHealthCheck()
            } catch {
                status = .error(error.localizedDescription)
                self.error = error.localizedDescription
            }
        }
    }
    
    func stop() {
        process?.terminate()
        process = nil
        checkTimer?.invalidate()
        checkTimer = nil
        status = .stopped
    }
    
    private func startBackendProcess() async throws {
        // First try to find bundled backend executable
        var backendPath = Bundle.main.resourcePath! + "/backend/ambient-backend"
        
        // If not found, try development paths
        if !FileManager.default.fileExists(atPath: backendPath) {
            // Try PyInstaller bundle in backend/dist
            let devPath = URL(fileURLWithPath: Bundle.main.bundlePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("backend/dist/ambient-backend/ambient-backend")
                .path
            
            if FileManager.default.fileExists(atPath: devPath) {
                backendPath = devPath
            } else {
                // Fall back to Python script for development
                let pythonPath = URL(fileURLWithPath: Bundle.main.bundlePath)
                    .deletingLastPathComponent()
                    .deletingLastPathComponent()
                    .deletingLastPathComponent()
                    .appendingPathComponent(".venv/bin/python")
                    .path
                
                let mainPath = URL(fileURLWithPath: Bundle.main.bundlePath)
                    .deletingLastPathComponent()
                    .deletingLastPathComponent()
                    .deletingLastPathComponent()
                    .appendingPathComponent("main.py")
                    .path
                
                if FileManager.default.fileExists(atPath: pythonPath) && 
                   FileManager.default.fileExists(atPath: mainPath) {
                    process = Process()
                    process?.executableURL = URL(fileURLWithPath: pythonPath)
                    process?.arguments = [mainPath, "--port", String(port)]
                    process?.environment = ProcessInfo.processInfo.environment
                    try process?.run()
                    return
                } else {
                    throw BackendError.notFound
                }
            }
        }
        
        process = Process()
        process?.executableURL = URL(fileURLWithPath: backendPath)
        process?.arguments = ["--port", String(port)]
        process?.environment = ProcessInfo.processInfo.environment
        
        try process?.run()
    }
    
    private func waitForBackend(timeout: TimeInterval = 30) async throws {
        let start = Date()
        
        while Date().timeIntervalSince(start) < timeout {
            if await checkHealth() {
                return
            }
            try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
        }
        
        throw BackendError.timeout
    }
    
    private func checkHealth() async -> Bool {
        guard let url = URL(string: "http://localhost:\(port)/health") else { return false }
        
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
    
    private func startHealthCheck() {
        checkTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { _ in
            Task { @MainActor in
                if await self.checkHealth() {
                    if case .error = self.status {
                        self.status = .running
                    }
                } else {
                    self.status = .error("Backend not responding")
                }
            }
        }
    }
}

enum BackendError: LocalizedError {
    case timeout
    case notFound
    
    var errorDescription: String? {
        switch self {
        case .timeout:
            return "Backend failed to start within timeout"
        case .notFound:
            return "Backend executable not found"
        }
    }
}
