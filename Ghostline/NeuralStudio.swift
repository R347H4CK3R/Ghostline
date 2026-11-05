import SwiftUI
import AVFoundation
import SpeechSynthesizer
import PocketTTS

/// Freely usable synthetic neural voices (not named celebrity replicas).
@MainActor
final class NeuralStudio: ObservableObject {
    @Published var engineName = "PocketTTS"
    @Published var voices: [TTSVoice] = []
    @Published var voiceID = ""
    @Published var state = "Choose an engine and prepare its model."
    @Published var busy = false
    @Published var generated: URL?
    @Published var installed = false
    private let pocket = PocketEngine()
    private var playback: AVAudioPlayer?

    func prepare() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            state = "Checking and preparing \(engineName) model. First setup requires downloading the free weights."
            try await pocket.prepare(onProgress: nil)
            voices = try await pocket.availableVoices()
            installed = true
            voiceID = voices.first?.id ?? ""
            state = "Ready: \(voices.count) real neural voices. Model is cached for offline use."
        } catch {
            state = "Model unavailable: \(error.localizedDescription)"
        }
    }
    func switchEngine(_ value: String) {
        engineName = value
        voices = []
        voiceID = ""
        installed = false
        generated = nil
        state = "Select Prepare Model to load \(value)."
    }
    func speak(_ words: String) async {
        guard installed, !busy else { state = "Prepare the model before speaking."; return }
        guard !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { state = "Enter text."; return }
        busy = true
        defer { busy = false }
        do {
            let selected = voices.first { $0.id == voiceID }
            var options = SynthesisOptions()
            options.voice = selected
            state = "Generating \(engineName) speech locally…"
            let sound: SpokenAudio
            sound = try await pocket.synthesize(words, options: options)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
            try sound.write(toWAV: url)
            let player = try AVAudioPlayer(contentsOf: url)
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            guard player.prepareToPlay() else { state = "Generated file cannot be played."; return }
            playback = player
            generated = url
            _ = player.play()
            state = "Generated verified playable WAV using \(selected?.name ?? "default") fully on-device."
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
            Section("Free offline neural engine") {
                Picker("Engine", selection: Binding(get: {neural.engineName}, set: {neural.switchEngine($0)})) {
                    Text("PocketTTS — speech presets").tag("PocketTTS")
                }
                Button(neural.busy ? "Processing…" : "Prepare model") { Task { await neural.prepare() } }.disabled(neural.busy)
                Text("The first installation downloads open-weight models. After they are cached, synthesis does not need a network connection. The initial download is not offline.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Neural voice library") {
                Text(neural.installed ? "\(neural.voices.count) available voices" : "Load the model to discover its voices.")
                if !neural.voices.isEmpty {
                    Picker("Voice", selection: $neural.voiceID) {
                        ForEach(neural.voices, id: \.id) { voice in
                            Text(voice.name).tag(voice.id)
                        }
                    }
                }
                TextEditor(text: $script).frame(minHeight: 85)
                Button("Generate and play offline WAV") { Task { await neural.speak(script) } }
                    .disabled(!neural.installed || neural.busy)
                if let generated = neural.generated {
                    ShareLink(item: generated) { Label("Save or share WAV", systemImage: "square.and.arrow.up") }
                }
            }
            Section("Model status") {
                Text(neural.state).font(.footnote)
                Text("These are distinct synthetic voices, not impersonations of the 215 named performers and fictional characters in the reference catalog.")
                    .font(.footnote).foregroundStyle(.secondary)
                Text("Models: Kokoro Apache-2.0. PocketTTS Kyutai CC BY 4.0 weights; some preset voices have additional noncommercial conditions. Consult each voice's license.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Neural Studio")
    }
}
