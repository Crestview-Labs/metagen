import SwiftUI

struct LogView: View {
    @ObservedObject var chatService: ChatService
    @State private var isExpanded = false
    
    var body: some View {
        DisclosureGroup(
            isExpanded: $isExpanded,
            content: {
                ScrollViewReader { proxy in
                    ScrollView {
                        Text(chatService.logs)
                            .font(.system(.caption, design: .monospaced))
                            .padding()
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                            .id("logs")
                    }
                    .frame(height: 200)
                    .background(Color.black.opacity(0.05))
                    .cornerRadius(8)
                    .onChange(of: chatService.logs) { _ in
                        withAnimation {
                            proxy.scrollTo("logs", anchor: .bottom)
                        }
                    }
                }
                
                HStack {
                    Button("Clear Logs") {
                        chatService.logs = ""
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.blue)
                    
                    Spacer()
                    
                    Text("\(chatService.logs.components(separatedBy: "\n").count - 1) lines")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 4)
            },
            label: {
                HStack {
                    Image(systemName: "doc.text.magnifyingglass")
                    Text("Debug Logs")
                    Spacer()
                }
                .font(.caption)
                .foregroundColor(.secondary)
            }
        )
        .padding()
    }
}