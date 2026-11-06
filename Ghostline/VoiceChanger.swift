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
    @State private var importingAudio = false

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
                .disabled(importingAudio)
                Button("Import an existing WAV or audio recording") { importAudio = true }
                    .disabled(recording || importingAudio)
                if let recordingURL {
                    Text(recordingURL.lastPathComponent).font(.caption).lineLimit(2)
                    ShareLink(item: recordingURL) {
                        Label("Save original recording to Files", systemImage: "square.and.arrow.up")
                    }
                }
                Text("Recordings stay on the iPhone and transfer privately to the converter. You can override the recording with the converter's Source Audio picker.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("3 • Offline voice conversion") {
                if let selected {
                    NavigationLink {
                        GhostlineRVCWebScreen(importedPack: selected, sourceAudioURL: recordingURL)
                    } label: {
                        Label("Convert into " + selected.name, systemImage: "waveform.path")
                    }
                    .tint(.purple)
                    .disabled(recording || importingAudio)
                    if recording {
                        Text("Stop recording before opening the converter.")
                            .font(.caption).foregroundStyle(.orange)
                    } else if recordingURL != nil {
                        Text("Your local recording will be handed directly to the converter, with SHA-256 checked. No Files export/re-import required.")
                            .font(.caption).foregroundStyle(.green)
                    }
                    Text("The converter needs local ContentVec and RMVPE files. It loads the chosen private model where supported, then accepts your source WAV/MP3. Playback and export appear after a successful conversion.")
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
                Task { await importSourceAudio(source) }
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

    /// Preflight and copy potentially large private audio off the UI thread.
    /// The WebAssembly converter's matching 128 MiB bound is checked again
    /// during the ephemeral localhost handoff (including SHA-256 validation).
    @MainActor
    private func importSourceAudio(_ source: URL) async {
        guard !recording && !importingAudio else {
            status = "Finish the current recording or import first."
            return
        }
        importingAudio = true
        defer { importingAudio = false }
        status = "Checking audio format and size before copying..."
        let result = await Task.detached(priority: .userInitiated) { () -> (URL?, String) in
            let granted = source.startAccessingSecurityScopedResource()
            defer { if granted { source.stopAccessingSecurityScopedResource() } }
            let ext = source.pathExtension.lowercased()
            guard ["wav", "mp3", "m4a", "caf"].contains(ext) else {
                return (nil, "Choose WAV, MP3, M4A or CAF audio.")
            }
            guard let attributes = try? FileManager.default.attributesOfItem(atPath: source.path),
                  (attributes[.type] as? FileAttributeType) == .typeRegular,
                  let byteCount = (attributes[.size] as? NSNumber)?.uint64Value,
                  byteCount > 44, byteCount <= 128 * 1024 * 1024 else {
                return (nil, "Recording is unavailable, empty or larger than 128 MiB.")
            }
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("ghostline-source-" + UUID().uuidString + "." + ext)
            do {
                try FileManager.default.copyItem(at: source, to: destination)
                return (destination, "")
            } catch {
                return (nil, "Could not copy the selected recording privately.")
            }
        }.value
        if let imported = result.0 {
            recordingURL = imported
            status = "Audio imported locally and ready for direct RVC handoff."
        } else {
            status = result.1
            GhostlineDiagnostics.shared.record("app", "file_import_failed")
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
        status = "Recording saved locally and ready for direct RVC handoff."
    }
}
