import SwiftUI
import AVFoundation
import UniformTypeIdentifiers
import FluidAudio

struct SavedClone: Codable, Identifiable, Hashable {
    var id: UUID
    var name: String
}

/// All processing is local once PocketTTS weights have been downloaded.
@MainActor
final class LocalCloneStudio: ObservableObject {
    @Published var clones: [SavedClone] = []
    @Published var chosenID: UUID?
    @Published var status = "Prepare the free PocketTTS engine to clone an authorized voice."
    @Published var busy = false
    @Published var modelReady = false
    @Published var outputURL: URL?
    private let engine = PocketTtsManager()
    private var player: AVAudioPlayer?
    private var rootDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("GHOSTLINE-PrivateClones", isDirectory: true)
    }
    private var indexURL: URL { rootDirectory.appendingPathComponent("index.json") }

    init() {
        if let bytes = try? Data(contentsOf: indexURL),
           let saved = try? JSONDecoder().decode([SavedClone].self, from: bytes) {
            clones = saved.filter { FileManager.default.fileExists(atPath: fileURL(for: $0).path) }
            chosenID = clones.first?.id
        }
    }

    private func fileURL(for clone: SavedClone) -> URL {
        rootDirectory.appendingPathComponent(clone.id.uuidString + ".bin")
    }
    private func persist() throws {
        try FileManager.default.createDirectory(at: rootDirectory, withIntermediateDirectories: true)
        try JSONEncoder().encode(clones).write(to: indexURL, options: .atomic)
    }

    func prepare() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            status = "Preparing PocketTTS weights. Initial model setup needs internet; later speech stays offline."
            try await engine.initialize()
            modelReady = true
            status = "PocketTTS model ready. Imported voice references are processed only on your iPhone."
        } catch { status = "Model preparation failed: \(error.localizedDescription)" }
    }

    func importSample(_ url: URL) async {
        guard modelReady, !busy else { status = "Prepare the model before importing."; return }
        let granted = url.startAccessingSecurityScopedResource()
        defer { if granted { url.stopAccessingSecurityScopedResource() } }
        busy = true
        defer { busy = false }
        do {
            status = "Extracting a voice profile locally…"
            let voiceData = try await engine.cloneVoice(from: url)
            let clone = SavedClone(id: UUID(), name: url.deletingPathExtension().lastPathComponent)
            try FileManager.default.createDirectory(at: rootDirectory, withIntermediateDirectories: true)
            try await engine.saveClonedVoice(voiceData, to: fileURL(for: clone))
            clones.append(clone)
            chosenID = clone.id
            try persist()
            status = "Voice profile created and saved locally. Ready to synthesize."
        } catch {
            status = "Voice sample rejected: \(error.localizedDescription). Use a clear 1–30 second recording."
        }
    }

    func generate(_ words: String) async {
        guard modelReady, !busy else { status = "Prepare PocketTTS first."; return }
        guard let clone = clones.first(where: {$0.id == chosenID}) else { status = "Select a saved voice clone."; return }
        guard !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { status = "Enter text."; return }
        busy = true
        defer { busy = false }
        do {
            status = "Synthesizing locally using \(clone.name)…"
            let data = try await engine.loadClonedVoice(from: fileURL(for: clone))
            let wav = try await engine.synthesize(text: words, voiceData: data)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
            try wav.write(to: url, options: .atomic)
            let playback = try AVAudioPlayer(contentsOf: url)
            guard playback.prepareToPlay() else { status = "Invalid audio file"; return }
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            player = playback
            outputURL = url
            _ = playback.play()
            status = "Playable cloned speech generated locally. Compare by listening to the authorized sample."
        } catch { status = "Voice synthesis failed: \(error.localizedDescription)" }
    }

    func deleteSelected() {
        guard let clone = clones.first(where: {$0.id == chosenID}) else { return }
        try? FileManager.default.removeItem(at: fileURL(for: clone))
        clones.removeAll { $0.id == clone.id }
        chosenID = clones.first?.id
        do { try persist(); status = "Local clone deleted." }
        catch { status = "Unable to update the local clone index." }
    }
}

struct CloneStudioView: View {
    @StateObject private var studio = LocalCloneStudio()
    @State private var words = "This is my own voice, now synthesized entirely on my phone."
    @State private var importing = false
    @State private var consent = false

    var body: some View {
        Form {
            Section("Offline cloning engine") {
                Button(studio.modelReady ? "Model prepared" : "Prepare free PocketTTS model") {
                    Task { await studio.prepare() }
                }.disabled(studio.busy || studio.modelReady)
                Text("One-time online model download; no subscription, API key, upload, or paid cloud inference. All cloning and synthesis happen locally thereafter.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Import authorized voice sample") {
                Toggle("I own this voice or have permission to clone it", isOn: $consent)
                Button("Import sample (1–30 seconds)") { importing = true }
                    .disabled(!studio.modelReady || studio.busy || !consent)
                Text("Select a clean WAV, MP3, or M4A recording. GHOSTLINE extracts a reusable local voice profile; it never uploads this recording.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("My local voice clones") {
                if studio.clones.isEmpty { Text("No profiles created yet.").foregroundStyle(.secondary) }
                else {
                    Picker("Voice profile", selection: $studio.chosenID) {
                        ForEach(studio.clones) { clone in Text(clone.name).tag(Optional(clone.id)) }
                    }
                    Button("Delete selected local clone", role: .destructive) { studio.deleteSelected() }
                }
                TextEditor(text: $words).frame(minHeight: 85)
                Button("Generate cloned speech offline") { Task { await studio.generate(words) } }
                    .disabled(studio.busy || studio.chosenID == nil || !studio.modelReady)
                if let url = studio.outputURL {
                    ShareLink(item: url) { Label("Save generated WAV", systemImage: "square.and.arrow.up") }
                }
            }
            Section("Status") {
                Text(studio.status)
                    .font(.footnote)
                Text("PocketTTS weights © Kyutai (CC BY 4.0). A functional clone's resemblance depends on recording quality; verified permission and actual playback are required.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Clone Studio")
        .fileImporter(isPresented: $importing, allowedContentTypes: [.audio]) { result in
            switch result {
            case .success(let url): Task { await studio.importSample(url) }
            case .failure(let error): studio.status = "File selection failed: \(error.localizedDescription)"
            }
        }
    }
}
