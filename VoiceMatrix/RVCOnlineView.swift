import SwiftUI
import UniformTypeIdentifiers

/// Online-only destination; native UI verification is required before release.
/// Requires the app-owned RVCOnlineStudio and the existing AudioStore environment.
struct RVCOnlineView: View {
    @EnvironmentObject private var rvc: RVCOnlineStudio
    @EnvironmentObject private var audio: AudioStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var importing = false
    @State private var confirmingStopTracking = false

    var body: some View {
        List {
            Section {
                Label("ONLINE SPEECH-TO-SPEECH ONLY", systemImage: "laptopcomputer")
                    .font(.caption.weight(.bold)).foregroundStyle(StudioPalette.mint)
                Text("Import your spoken audio to convert it on your paired laptop. The laptop and its RVC service must stay available.")
                Text("Offline RVC and text-to-speech are unavailable. Your existing voices and saved recordings are unchanged.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("1 · Choose a laptop model") {
                Picker("RVC model", selection: $rvc.selectedID) {
                    Text("Choose a model").tag("")
                    ForEach(rvc.catalog?.models ?? []) { model in Text(model.name).tag(model.id) }
                }.disabled(rvc.working || rvc.pausing || rvc.pending)
                    .accessibilityIdentifier("rvc-model-picker")
                if let model = rvc.selected {
                    Text(model.categories.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                    Text("Identity and likeness unverified").font(.caption).foregroundStyle(.secondary)
                }
                if rvc.catalog?.models.isEmpty == true { Text("No RVC models are available on this laptop.").foregroundStyle(.secondary) }
                Button("Refresh models") { rvc.refreshCatalog() }
                    .disabled(rvc.working || rvc.pausing || rvc.pending)
                    .accessibilityIdentifier("rvc-refresh-models")
            }
            Section("2 · Import your spoken audio") {
                Button { importing = true } label: { Label("Import WAV", systemImage: "waveform.badge.plus") }
                    .disabled(rvc.working || rvc.pausing || rvc.pending)
                    .accessibilityIdentifier("rvc-import-wav")
                if let input = rvc.input {
                    Text(input.name).font(.headline).accessibilityIdentifier("rvc-input-name")
                    Text(String(format: "%.2f seconds · %d Hz · %@", input.seconds, input.sampleRate,
                                ByteCountFormatter.string(fromByteCount: Int64(input.data.count), countStyle: .file)))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("Mono PCM16 WAV, 0.2–30 seconds, up to 3 MiB. Accepted rates: 16, 22.05, 24, 32, 40, 44.1 or 48 kHz. The app does not resample or change your selected file.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("3 · Convert on your laptop") {
                Text("Tapping Send uploads this WAV to your paired laptop. The laptop keeps the input and result; this screen does not delete them.")
                    .font(.caption).foregroundStyle(.secondary)
                Button { rvc.send(audio: audio) } label: {
                    Label("Send audio to laptop", systemImage: "arrow.up.circle.fill")
                        .font(.headline).frame(maxWidth: .infinity, minHeight: 48)
                }.buttonStyle(.borderedProminent)
                    .disabled(!rvc.canSend || audio.microphoneInUse || audio.processingInUse)
                    .accessibilityIdentifier("rvc-send-audio")
                if rvc.working { ProgressView(rvc.operationLabel).accessibilityIdentifier("rvc-local-operation") }
                Text(rvc.stage).font(.headline).accessibilityIdentifier("rvc-job-stage")
                if !rvc.submittedName.isEmpty, rvc.state.requestID != nil {
                    Text("Request model: " + rvc.submittedName).font(.caption).foregroundStyle(.secondary)
                }
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    VStack(alignment: .leading, spacing: 6) {
                        LabeledContent("Last laptop activity", value: activityTime)
                        LabeledContent("Last successful check", value: rvc.lastChecked?.formatted(date: .abbreviated, time: .standard) ?? "Not checked")
                        Text(freshness(at: context.date)).font(.caption)
                            .foregroundStyle(.secondary).accessibilityIdentifier("rvc-connection-freshness")
                    }.font(.caption)
                }
                if let error = rvc.state.connectionError { Text(error).font(.caption).foregroundStyle(.orange) }
                Text(rvc.message).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("rvc-message")
                HStack {
                    Button("Refresh") { rvc.refresh() }.accessibilityIdentifier("rvc-refresh-request")
                    Button("Reconnect") { rvc.reconnect() }.accessibilityIdentifier("rvc-reconnect")
                }.disabled(rvc.working || rvc.pausing)
                if rvc.pending {
                    Button(rvc.state.phase == .cancellationUnconfirmed ? "Retry cancellation" : "Request cancellation", role: .destructive) { rvc.cancel() }
                        .disabled(rvc.pausing || rvc.cancellationInFlight).accessibilityIdentifier("rvc-cancel")
                    Button("Stop tracking this request") { confirmingStopTracking = true }
                        .disabled(rvc.pausing).accessibilityIdentifier("rvc-stop-tracking")
                    Text("Checks run while this screen is active, no more often than every 30 seconds automatically. Leaving the screen stops checks, not the laptop job.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if rvc.state.phase == .disconnected {
                    Button("Retry the same submission") { rvc.retrySubmission() }
                        .disabled(rvc.working || rvc.pausing).accessibilityIdentifier("rvc-retry-submission")
                    Text("This sends the same audio with the same request ID. It does not create a new conversion if the laptop already accepted it.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("4 · Listen or save") {
                if let output = rvc.output {
                    Text("Result from " + rvc.submittedName).font(.caption).foregroundStyle(.secondary)
                    AudioActions(url: output)
                } else {
                    Text("Audio appears here only after the result and its checksum are verified.").foregroundStyle(.secondary)
                }
                Text("Current-request tracking is kept for this app session. Closing the app does not cancel or erase the laptop job.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Laptop RVC")
        .scrollContentBackground(.hidden)
        .background(StudioPalette.background)
        .fileImporter(isPresented: $importing, allowedContentTypes: [.wav]) { result in
            switch result {
            case .success(let url): rvc.importWAV(url)
            case .failure: rvc.importerCancelled()
            }
        }
        .confirmationDialog("Stop tracking this request?", isPresented: $confirmingStopTracking, titleVisibility: .visible) {
            Button("Stop tracking", role: .destructive) { rvc.stopTracking() }
            Button("Keep tracking", role: .cancel) {}
        } message: {
            Text("The laptop may still be processing it. This stops local checks only; it does not cancel the job or delete its audio. You can then choose a new request.")
        }
        .task { await rvc.observeWhileVisible() }
        .onChange(of: scenePhase, initial: true) { _, phase in rvc.setActive(phase == .active) }
        .onDisappear { if audio.playing == rvc.output { audio.stop() } }
    }
    private var activityTime: String {
        guard let stamp = rvc.state.receipt?.updatedAt else { return "Not reported" }
        guard stamp <= Date.distantFuture.timeIntervalSince1970 else { return "Outside the device date range" }
        return Date(timeIntervalSince1970: stamp).formatted(date: .abbreviated, time: .standard)
    }
    private func freshness(at now: Date) -> String {
        switch RVCOnlineRefreshSchedule.freshness(checkedAt: rvc.lastChecked, now: now, reachable: rvc.reachable) {
        case .neverChecked: return "Connection has not been confirmed."
        case .recent: return "Connection checked recently. An unchanged activity time can mean the laptop is still waiting or converting."
        case .stale: return "Connection check is stale. Refresh to confirm the laptop's current status."
        case .disconnected: return "Not currently connected. The last successful check is shown above."
        }
    }
}
