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
