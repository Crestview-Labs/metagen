import SwiftUI

struct MessageView: View {
    let message: ChatMessage
    
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Avatar - only show for user messages or first assistant message in turn
            if message.role == .user || message.isFirstInTurn {
                Circle()
                    .fill(message.role == .user ? Color.blue : Color.gray)
                    .frame(width: 32, height: 32)
                    .overlay(
                        Text(message.role == .user ? "U" : "A")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white)
                    )
            } else {
                // Placeholder space for alignment when no avatar
                Color.clear
                    .frame(width: 32, height: 32)
            }
            
            // Message content
            VStack(alignment: .leading, spacing: 4) {
                // Only show role label for user messages or first assistant message in turn
                if message.role == .user || message.isFirstInTurn {
                    Text(message.role == .user ? "You" : "Assistant")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Text(message.content)
                    .font(.body)
                    .textSelection(.enabled)
                
                // Only show timestamp for user messages or first assistant message in turn
                if message.role == .user || message.isFirstInTurn {
                    Text(message.timestamp, style: .time)
                        .font(.caption2)
                        .foregroundColor(Color.secondary)
                }
            }
            
            Spacer()
        }
        .padding(.horizontal)
    }
}