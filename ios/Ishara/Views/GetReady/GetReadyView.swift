import SwiftUI

/// Screen 2: framing checklist and 2 s hands-at-rest calibration, then Start call.
struct GetReadyView: View {
    @State private var model = GetReadyModel()
    let onStart: () -> Void
    let onBack: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Prop the phone about an arm away.")
                        .font(.title3)

                    CameraPreviewPlaceholder(
                        state: nil,
                        message: "Camera preview\nstick-figure overlay drawn on your body",
                        minHeight: 240
                    )

                    ChecklistCard(passed: model.passedChecks)
                    CalibrationCard(progress: model.calibrationProgress, isActive: model.allChecksPassed)
                }
                .padding()
            }
            .navigationTitle("Get ready")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Back", action: onBack)
                }
            }
            .safeAreaInset(edge: .bottom) {
                Button(action: onStart) {
                    Label("I'm ready, start call", systemImage: "phone.arrow.up.right.fill")
                }
                .buttonStyle(.bigAction(.green))
                .disabled(!model.isReady)
                .padding()
                .background(.bar)
            }
            .task { await model.runSimulatedChecks() }
        }
    }
}

private struct ChecklistCard: View {
    let passed: Set<GetReadyModel.Check>

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(GetReadyModel.Check.allCases) { check in
                let isPassed = passed.contains(check)
                Label {
                    Text(check.title)
                } icon: {
                    Image(systemName: isPassed ? "checkmark.circle.fill" : "circle.dotted")
                        .foregroundStyle(isPassed ? .green : .secondary)
                }
                .font(.title3)
                .accessibilityLabel("\(check.title): \(isPassed ? "yes" : "checking")")
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.green.opacity(0.15), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private struct CalibrationCard: View {
    let progress: Double
    let isActive: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(progress >= 1 ? "Hands at rest: calibrated" : "Rest your hands on the table…")
                .font(.headline)
            ProgressView(value: progress)
                .tint(.orange)
            Text(remainingText)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.yellow.opacity(0.2), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private var remainingText: String {
        guard isActive else { return "Starts once the checklist is done." }
        let remaining = max(0, GetReadyModel.calibrationSeconds * (1 - progress))
        return progress >= 1 ? "Done" : String(format: "%.1f s left", remaining)
    }
}

#Preview {
    GetReadyView(onStart: {}, onBack: {})
}
