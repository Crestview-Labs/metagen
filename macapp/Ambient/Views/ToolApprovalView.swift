import SwiftUI

struct ToolApprovalView: View {
    let approval: ToolApprovalRequest
    let onApprove: () -> Void
    let onReject: (String?) -> Void
    
    @State private var showRejectReason = false
    @State private var rejectReason = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.orange)
                    .font(.title2)
                
                Text("Tool Approval Required")
                    .font(.headline)
            }
            
            VStack(alignment: .leading, spacing: 8) {
                Text("Tool: **\(approval.tool.name)**")
                    .font(.system(.body, design: .monospaced))
                
                if !approval.tool.parameters.isEmpty {
                    Text("Parameters:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    ForEach(Array(approval.tool.parameters.keys), id: \.self) { key in
                        HStack {
                            Text(key)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.secondary)
                            Text(":")
                            Text("\(String(describing: approval.tool.parameters[key] ?? "nil"))")
                                .font(.system(.caption, design: .monospaced))
                                .lineLimit(2)
                        }
                        .padding(.leading, 8)
                    }
                }
            }
            
            if showRejectReason {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Rejection reason (optional):")
                        .font(.caption)
                    
                    TextField("Enter reason...", text: $rejectReason)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .font(.system(.body, design: .monospaced))
                }
            }
            
            HStack(spacing: 12) {
                Button(action: {
                    if showRejectReason {
                        onReject(rejectReason.isEmpty ? nil : rejectReason)
                    } else {
                        showRejectReason = true
                    }
                }) {
                    HStack {
                        Image(systemName: "xmark.circle")
                        Text(showRejectReason ? "Confirm Reject" : "Reject")
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.regular)
                
                if showRejectReason {
                    Button("Cancel") {
                        showRejectReason = false
                        rejectReason = ""
                    }
                    .buttonStyle(.plain)
                    .controlSize(.regular)
                }
                
                Spacer()
                
                Button(action: onApprove) {
                    HStack {
                        Image(systemName: "checkmark.circle")
                        Text("Approve")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.regular)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.orange.opacity(0.3), lineWidth: 1)
        )
    }
}