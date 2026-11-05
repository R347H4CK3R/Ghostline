import SwiftUI
import AVFoundation
import FluidAudio

@MainActor
final class KokoroOfflineStudio: ObservableObject {
    @Published var language = "English"
    @Published var voiceID = "af_heart"
    @Published var prepared = false
    @Published var busy = false
    @Published var status = "Select a language and prepare the free Kokoro CoreML engine."
    @Published var output: URL?
    private var engine = KokoroAneManager(variant: .english)
    private var player: AVAudioPlayer?

    var voices: [String] {
        switch language {
        case "Mandarin": return KokoroAneConstants.mandarinVoices
        case "Japanese": return KokoroAneConstants.japaneseVoices
        case "Spanish": return KokoroAneConstants.spanishVoices
        case "French": return KokoroAneConstants.frenchVoices
        default: return KokoroAneConstants.englishVoices
        }
    }
    func changeLanguage(_ value: String) {
        language = value
        prepared = false
        output = nil
        let variant: KokoroAneVariant
        switch value {
        case "Mandarin": variant = .mandarin
        case "Japanese": variant = .japanese
        case "Spanish": variant = .spanish
        case "French": variant = .french
        default: variant = .english
        }
        engine = KokoroAneManager(variant: variant)
        voiceID = voices.first ?? "af_heart"
        status = "Prepare the \(language) model before speech generation."
    }
    func prepare() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            status = "Preparing \(language) neural model. First setup downloads free weights."
            try await engine.initialize()
            prepared = true
            status = "Kokoro \(language) ready. \(voices.count) voice pack identifiers; only selected packs download as needed."
        } catch { status = "Model setup failed: \(error.localizedDescription)" }
    }
    func generate(_ text: String) async {
        guard prepared, !busy else { status = "Prepare the model first."; return }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { status = "Enter some text."; return }
        busy = true
        defer { busy = false }
        do {
            status = "Generating \(voiceID) entirely on the iPhone..."
            let wav = try await engine.synthesize(text: text, voice: voiceID)
            let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
            try wav.write(to: file, options: .atomic)
            let result = try AVAudioPlayer(contentsOf: file)
            guard result.prepareToPlay() else { status = "Generated WAV not playable."; return }
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            player = result
            output = file
            _ = result.play()
            status = "Generated playable offline neural audio with \(voiceID)."
        } catch { status = "Generation failed: \(error.localizedDescription)" }
    }
}

struct KokoroOfflineView: View {
    @StateObject private var studio = KokoroOfflineStudio()
    @State private var script = "Welcome to Ghostline. This is a free offline neural voice."
    private let languages = ["English","Mandarin","Japanese","Spanish","French"]
    var body: some View {
        Form {
            Section("Kokoro neural model") {
                Picker("Language", selection: Binding(get: { studio.language }, set: { studio.changeLanguage($0) })) {
                    ForEach(languages, id: \.self) { Text($0).tag($0) }
                }
                Button(studio.prepared ? "Model ready" : "Prepare model") { Task { await studio.prepare() } }
                    .disabled(studio.busy || studio.prepared)
                Text("First use downloads the model files. Later synthesis uses CoreML on-device. Other voice packs may need one-time downloads before offline playback.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Ready-made voice packs") {
                Text("\(studio.voices.count) published identifiers for \(studio.language); functionality is verified only after local audio plays.")
                    .font(.footnote).foregroundStyle(.secondary)
                Picker("Voice",selection:$studio.voiceID) {
                    ForEach(studio.voices,id:\.self) { Text($0).tag($0) }
                }
                TextEditor(text: $script).frame(minHeight:80)
                Button("Generate offline speech") { Task { await studio.generate(script) } }
                    .disabled(studio.busy || !studio.prepared)
                if let output = studio.output {
                    ShareLink(item: output) { Label("Save or share WAV",systemImage:"square.and.arrow.up") }
                }
            }
            Section("Status") {
                Text(studio.status).font(.footnote)
                Text("Free Kokoro model, Apache-2.0. Voices are synthetic, not authorized celebrity identity clones.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Kokoro Offline Voices")
    }
}
