import SwiftUI

struct HeaderView: View {
    @EnvironmentObject var backendManager: BackendManager
    
    var body: some View {
        HStack {
            Text("Ambient")
                .font(.title2)
                .bold()
            
            Spacer()
            
            // Backend status indicator
            HStack(spacing: 4) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)
                
                Text(statusText)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }
    
    private var statusColor: Color {
        switch backendManager.status {
        case .running:
            return .green
        case .starting:
            return .orange
        case .stopped:
            return .gray
        case .error:
            return .red
        }
    }
    
    private var statusText: String {
        switch backendManager.status {
        case .running:
            return "Connected"
        case .starting:
            return "Connecting..."
        case .stopped:
            return "Disconnected"
        case .error(let message):
            return "Error: \(message)"
        }
    }
}