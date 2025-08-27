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
                        
                        // Tool Approval UI
                        if let approval = chatViewModel.pendingApproval {
                            ToolApprovalView(
                                approval: approval,
                                onApprove: chatViewModel.approveTool,
                                onReject: chatViewModel.rejectTool
                            )
                            .id("approval-\(approval.id)")
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
                .onChange(of: chatViewModel.pendingApproval?.id) { _ in
                    if let approval = chatViewModel.pendingApproval {
                        withAnimation {
                            proxy.scrollTo("approval-\(approval.id)", anchor: .bottom)
                        }
                    }
                }
            }
            
            Divider()
            
            // Input
            ChatInputView()
                .padding()
            
            // Debug Logs (collapsible)
            LogView(chatService: chatViewModel.chatService)
                .background(Color(NSColor.controlBackgroundColor))
        }
        .onAppear {
            backendManager.start()
        }
    }
}
