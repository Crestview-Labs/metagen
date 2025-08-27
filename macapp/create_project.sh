#!/bin/bash

# Create Xcode project structure for Ambient Mac App
echo "Creating Ambient Mac App project structure..."

# Create directory structure
mkdir -p Ambient
mkdir -p Ambient/Resources
mkdir -p Ambient/Views
mkdir -p Ambient/Models
mkdir -p Ambient/Services
mkdir -p Ambient/Utils

# Create Info.plist
cat > Ambient/Info.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>$(DEVELOPMENT_LANGUAGE)</string>
    <key>CFBundleExecutable</key>
    <string>$(EXECUTABLE_NAME)</string>
    <key>CFBundleIconFile</key>
    <string></string>
    <key>CFBundleIdentifier</key>
    <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundlePackageType</key>
    <string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>$(MACOSX_DEPLOYMENT_TARGET)</string>
    <key>NSMainStoryboardFile</key>
    <string>Main</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
</dict>
</plist>
EOF

# Create main app file
cat > Ambient/AmbientApp.swift << 'EOF'
import SwiftUI

@main
struct AmbientApp: App {
    @StateObject private var chatViewModel = ChatViewModel()
    @StateObject private var backendManager = BackendManager()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(chatViewModel)
                .environmentObject(backendManager)
                .frame(minWidth: 800, minHeight: 600)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandGroup(after: .appInfo) {
                Button("Clear Conversation") {
                    chatViewModel.clearMessages()
                }
                .keyboardShortcut("k", modifiers: [.command])
            }
        }
    }
}
EOF

# Create ContentView
cat > Ambient/Views/ContentView.swift << 'EOF'
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var chatViewModel: ChatViewModel
    @EnvironmentObject var backendManager: BackendManager
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HeaderView()
                .padding()
                .background(Color(NSColor.controlBackgroundColor))
            
            Divider()
            
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(chatViewModel.messages) { message in
                            MessageView(message: message)
                                .id(message.id)
                        }
                        
                        if chatViewModel.isStreaming {
                            StreamingIndicator()
                        }
                    }
                    .padding()
                }
                .onChange(of: chatViewModel.messages.count) { _ in
                    withAnimation {
                        proxy.scrollTo(chatViewModel.messages.last?.id, anchor: .bottom)
                    }
                }
            }
            
            Divider()
            
            // Input
            ChatInputView()
                .padding()
        }
        .onAppear {
            backendManager.start()
        }
    }
}
EOF

# Create ChatViewModel
cat > Ambient/Models/ChatViewModel.swift << 'EOF'
import Foundation
import Combine
import MetagenAPI

@MainActor
class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isStreaming = false
    @Published var inputText = ""
    @Published var error: String?
    
    private var cancellables = Set<AnyCancellable>()
    private let chatService: ChatService
    
    init() {
        self.chatService = ChatService()
        setupWelcomeMessage()
    }
    
    private func setupWelcomeMessage() {
        let welcome = ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            content: "🤖 Welcome to Ambient!\n\nI'm here to help with your tasks. You can ask me anything!",
            timestamp: Date()
        )
        messages.append(welcome)
    }
    
    func sendMessage(_ content: String) {
        guard !content.isEmpty else { return }
        
        // Add user message
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            role: .user,
            content: content,
            timestamp: Date()
        )
        messages.append(userMessage)
        
        // Clear input
        inputText = ""
        
        // Start streaming response
        isStreaming = true
        
        Task {
            do {
                let response = try await chatService.sendMessage(content)
                await handleStreamResponse(response)
            } catch {
                self.error = error.localizedDescription
                isStreaming = false
            }
        }
    }
    
    private func handleStreamResponse(_ stream: AsyncThrowingStream<ChatEvent, Error>) async {
        var assistantMessage = ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            content: "",
            timestamp: Date()
        )
        messages.append(assistantMessage)
        let messageIndex = messages.count - 1
        
        do {
            for try await event in stream {
                switch event {
                case .message(let content):
                    messages[messageIndex].content += content
                case .toolUse(let tool):
                    // Handle tool approval if needed
                    break
                case .done:
                    isStreaming = false
                }
            }
        } catch {
            self.error = error.localizedDescription
            isStreaming = false
        }
    }
    
    func clearMessages() {
        messages.removeAll()
        setupWelcomeMessage()
    }
}

struct ChatMessage: Identifiable {
    let id: String
    let role: MessageRole
    var content: String
    let timestamp: Date
}

enum MessageRole {
    case user
    case assistant
    case system
}
EOF

# Create BackendManager
cat > Ambient/Services/BackendManager.swift << 'EOF'
import Foundation
import Combine

@MainActor
class BackendManager: ObservableObject {
    @Published var status: BackendStatus = .stopped
    @Published var port: Int = 8985
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
        let backendPath = Bundle.main.resourcePath! + "/backend/ambient-backend"
        
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
EOF

# Create Package.swift for Swift Package Manager
cat > Package.swift << 'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Ambient",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Ambient", targets: ["Ambient"])
    ],
    dependencies: [
        .package(path: "../api/swift")
    ],
    targets: [
        .executableTarget(
            name: "Ambient",
            dependencies: [
                .product(name: "MetagenAPI", package: "swift")
            ],
            path: "Ambient"
        )
    ]
)
EOF

# Create basic xcodeproj using Swift package
echo "Generating Xcode project from Package.swift..."
swift package generate-xcodeproj

# Make script executable
chmod +x create_project.sh

echo "✅ Project structure created!"
echo ""
echo "Next steps:"
echo "1. Open Ambient.xcodeproj in Xcode"
echo "2. Set up code signing (if needed)"
echo "3. Build and run the app"
echo ""
echo "The project references the MetagenAPI package from ../api/swift"