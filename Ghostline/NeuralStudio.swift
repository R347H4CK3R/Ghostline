import SwiftUI
import AVFoundation
import FluidAudio

// Kyutai PocketTTS English preset IDs from the published model pack.
// Voice-specific licenses remain in effect; this is not a celebrity catalog.
@MainActor
final class NeuralStudio: ObservableObject {
    struct Voice: Identifiable {
        let id: String
        let license: String
        var name: String { id.replacingOccurrences(of: "_", with: " ").capitalized }
    }
    let voices: [Voice] = [
        .init(id:"alba",license:"CC BY 4.0"),
        .init(id:"anna",license:"CC BY 4.0"),
        .init(id:"azelma",license:"CC BY 4.0"),
        .init(id:"bill_boerst",license:"CC0"),
        .init(id:"caro_davy",license:"CC0"),
        .init(id:"charles",license:"CC BY 4.0"),
        .init(id:"cosette",license:"CC BY-NC 4.0"),
        .init(id:"eponine",license:"CC BY 4.0"),
        .init(id:"eve",license:"CC BY 4.0"),
        .init(id:"fantine",license:"CC BY 4.0"),
        .init(id:"george",license:"CC BY 4.0"),
        .init(id:"jane",license:"CC BY 4.0"),
        .init(id:"javert",license:"CC0"),
        .init(id:"jean",license:"CC BY-NC 4.0"),
        .init(id:"marius",license:"CC0"),
        .init(id:"mary",license:"CC BY 4.0"),
        .init(id:"michael",license:"CC BY 4.0"),
        .init(id:"paul",license:"CC BY 4.0"),
        .init(id:"peter_yearsley",license:"CC0"),
        .init(id:"stuart_bell",license:"CC0"),
        .init(id:"vera",license:"CC BY 4.0")
    ]

    @Published var voiceID = "alba"
    @Published var state = "Prepare the free PocketTTS CoreML model."
    @Published var busy = false
    @Published var generated: URL?
    @Published var installed = false
    private let pocket = PocketTtsManager()
    private var playback: AVAudioPlayer?

    func prepare() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            state = "Preparing PocketTTS model. First setup needs a model download."
            try await pocket.initialize()
            installed = true
            state = "Ready: \(voices.count) published preset voice IDs; audio still needs device testing."
        } catch {
            state = "Model unavailable: \(error.localizedDescription)"
        }
    }
    func speak(_ words: String) async {
        guard installed, !busy else { state = "Prepare the model first."; return }
        guard !words.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else { state = "Enter text."; return }
        busy = true
        defer { busy = false }
        do {
            state = "Generating locally with \(voiceID)…"
            let wav = try await pocket.synthesize(text:words, voice:voiceID)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
            try wav.write(to:url, options:.atomic)
            let player = try AVAudioPlayer(contentsOf:url)
            guard player.duration > 0.2, player.prepareToPlay() else {
                state = "Generated output is not decodable."
                return
            }
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            playback = player
            generated = url
            _ = player.play()
            state = "Decodable WAV generated with \(voiceID)."
        } catch {
            state = "Neural synthesis failed: \(error.localizedDescription)"
        }
    }
}

struct NeuralStudioView: View {
    @StateObject private var neural = NeuralStudio()
    @State private var script = "What's your favorite scary movie?"
    var body: some View {
        Form {
            Section("PocketTTS • Free offline neural voices") {
                Button(neural.busy ? "Processing…" : "Prepare model") {
                    Task { await neural.prepare() }
                }.disabled(neural.busy || neural.installed)
                Text("First setup downloads open-weight assets; once cached, synthesis runs locally without an API. No subscription required.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Ready-made voices") {
                Picker("Voice", selection:$neural.voiceID) {
                    ForEach(neural.voices) { v in
                        Text(v.name + (v.license.contains("NC") ? " (Non-commercial)" : "")).tag(v.id)
                    }
                }
                TextEditor(text:$script).frame(minHeight:85)
                Button("Generate and play offline WAV") {
                    Task { await neural.speak(script) }
                }.disabled(!neural.installed || neural.busy)
                if let output = neural.generated {
                    ShareLink(item:output) { Label("Export WAV",systemImage:"square.and.arrow.up") }
                }
            }
            Section("Status") {
                Text(neural.state).font(.footnote)
                Text("Voices are synthetic presets, not actor or character clones. Kyutai PocketTTS weights CC BY 4.0, with separate voice-specific licenses.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.navigationTitle("PocketTTS Offline")
    }
}
