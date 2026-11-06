import SwiftUI
import AVFoundation
import UniformTypeIdentifiers

/// Guiding workflow for the existing experimental local RVC converter.
/// Batch WAV conversion is distinct from live microphone monitoring.
struct GhostlineVoiceChangerView: View {
    @StateObject private var library = RVCPackLibrary()
    @State private var selectedID: UUID?
    @State private var recordingURL: URL?
    @State private var recorder: AVAudioRecorder?
    @State private var recording = false
    @State private var status = "Choose an authorized imported RVC voice to get started."
    @State private var importAudio = false

    private var selected: RVCPackRecord? {
        library.packs.first { $0.id == selectedID }
    }

    var body: some View {
        Form {
            Section {
                Label("Voice Changer", systemImage: "waveform.badge.mic")
                    .font(.title2.bold()).foregroundStyle(.purple)
                Text("Choose a voice → record or import speech → convert offline → listen and export.")
                    .font(.subheadline)
                Text("Experimental batch conversion: this is not a live real-time microphone effect. No downloaded RVC model is considered verified until iPhone playback succeeds.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("1 • Choose a voice") {
                if library.packs.isEmpty {
                    Text("No RVC packs installed yet.")
                        .foregroundStyle(.secondary)
                    NavigationLink("Browse free community voices") { GhostlineCommunityVoicesView() }
                    NavigationLink("Import your .pth / .index pack") { RVCPackLibraryView() }
                } else {
                    Picker("Selected voice", selection: $selectedID) {
                        Text("Choose an imported model").tag(nil as UUID?)
                        ForEach(library.packs) { pack in
                            Text(pack.name + (pack.indexFile == nil ? " • no index" : " • index attached"))
                                .tag(Optional(pack.id))
                        }
                    }
                    Text("Only authorized private candidates are shown. A .index is optional for the experimental converter because index retrieval is not yet implemented.")
                        .font(.caption).foregroundStyle(.secondary)
                    NavigationLink("Manage installed RVC models") { RVCPackLibraryView() }
                }
            }
            Section("2 • Record or select speech") {
                Button(recording ? "Stop recording" : "Record your voice") {
                    if recording { stopRecording() }
                    else { Task { await startRecording() } }
                }
                .tint(recording ? .red : .purple)
                Button("Import an existing WAV or audio recording") { importAudio = true }
                if let recordingURL {
                    Text(recordingURL.lastPathComponent).font(.caption).lineLimit(2)
                    ShareLink(item: recordingURL) {
                        Label("Save original recording to Files", systemImage: "square.and.arrow.up")
                    }
                }
                Text("Recordings stay on your iPhone. The selected WAV or MP3 is handed directly to the offline converter through a temporary local route.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("3 • Offline voice conversion") {
                if let selected {
                    NavigationLink {
                        GhostlineRVCWebScreen(importedPack: selected, sourceAudio: recordingURL)
                    } label: {
                        Label("Convert into " + selected.name, systemImage: "waveform.path")
                    }
                    .tint(.purple)
                    Text("The converter needs local ContentVec and RMVPE files. Your selected recording is preloaded automatically. Playback and export appear only after a successful conversion.")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("Choose an imported RVC voice in Step 1 to enable conversion.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("No internet inference API is used by the experimental converter. Physical iPhone/Strata conversion has not been confirmed.")
                    .font(.caption).foregroundStyle(.orange)
            }
            Section("Status") {
                Text(status).font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Voice Changer")
        .fileImporter(isPresented: $importAudio, allowedContentTypes: [.audio, .data]) { result in
            switch result {
            case .success(let source):
                let granted = source.startAccessingSecurityScopedResource()
                defer { if granted { source.stopAccessingSecurityScopedResource() } }
                do {
                    let ext = source.pathExtension.lowercased()
                    guard ["wav", "mp3"].contains(ext) else {
                        status = "Choose a WAV or MP3 recording. Other formats are not yet supported by the converter."
                        GhostlineDiagnostics.shared.record("app", "file_import_failed")
                        return
                    }
                    let destination = FileManager.default.temporaryDirectory
                        .appendingPathComponent("ghostline-source-" + UUID().uuidString + "." + ext)
                    try FileManager.default.copyItem(at: source, to: destination)
                    recordingURL = destination
                    status = "Source audio imported privately and ready for the converter."
                } catch {
                    status = "Could not import source recording."
                    GhostlineDiagnostics.shared.record("app", "file_import_failed")
                }
            case .failure:
                status = "Audio import cancelled or unavailable."
            }
        }
        .onAppear {
            library.reloadCatalogFromDisk()
            if selectedID == nil { selectedID = library.packs.first?.id }
        }
        .onDisappear {
            if recording { stopRecording() }
        }
    }

    @MainActor
    private func startRecording() async {
        let granted = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            AVAudioApplication.requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard granted else {
            status = "Microphone permission is required for recording."
            GhostlineDiagnostics.shared.record("app", "audio_generation_failed")
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
            try session.setActive(true)
            let path = FileManager.default.temporaryDirectory
                .appendingPathComponent("ghostline-original-" + UUID().uuidString + ".wav")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatLinearPCM),
                AVSampleRateKey: 44100,
                AVNumberOfChannelsKey: 1,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false
            ]
            let candidate = try AVAudioRecorder(url: path, settings: settings)
            guard candidate.record() else { status = "Recording could not start."; return }
            recorder = candidate
            recordingURL = path
            recording = true
            status = "Recording your voice locally…"
        } catch {
            status = "Microphone recording failed."
            GhostlineDiagnostics.shared.record("app", "audio_generation_failed")
        }
    }

    private func stopRecording() {
        recorder?.stop()
        recorder = nil
        recording = false
        status = "Recording saved locally and ready to send directly to the converter."
    }
}
