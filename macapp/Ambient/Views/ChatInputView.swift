import SwiftUI

struct ChatInputView: View {
    @EnvironmentObject var chatViewModel: ChatViewModel
    @EnvironmentObject var backendManager: BackendManager
    @FocusState private var isFocused: Bool
    
    var body: some View {
        HStack(spacing: 12) {
            TextField("Type a message or /help for commands...", text: $chatViewModel.inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.body)
                .lineLimit(1...5)
                .focused($isFocused)
                .onSubmit {
                    sendMessage()
                }
                .disabled(!backendManager.status.isRunning)
            
            Button(action: sendMessage) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
            }
            .buttonStyle(.plain)
            .foregroundColor(canSend ? .accentColor : .gray)
            .disabled(!canSend)
            .keyboardShortcut(.return, modifiers: [])
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .onAppear {
            isFocused = true
        }
    }
    
    private var canSend: Bool {
        !chatViewModel.inputText.isEmpty && 
        backendManager.status.isRunning && 
        !chatViewModel.isStreaming
    }
    
    private func sendMessage() {
        guard canSend else { return }
        chatViewModel.sendMessage(chatViewModel.inputText)
    }
}