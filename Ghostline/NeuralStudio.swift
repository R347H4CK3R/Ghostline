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
    let evidence = GhostlineNeuralAudioEvidence()
    private let pocket = PocketTtsManager()

    func clearOutput() {
        generated = nil
        evidence.reset()
    }

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
        clearOutput()
        let selectedVoice = voiceID
        defer { busy = false }
        do {
            state = "Generating locally with \(selectedVoice)…"
            let wav = try await pocket.synthesize(text:words, voice:selectedVoice)
            generated = try evidence.acceptGeneratedWAV(wav, engine: "PocketTTS", voiceID: selectedVoice)
            state = "PocketTTS produced a validated WAV for \(selectedVoice); offline isolation and identity remain unverified."
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
                .disabled(neural.busy)
                .onChange(of: neural.voiceID) { _, _ in neural.clearOutput() }
                TextEditor(text:$script).frame(minHeight:85)
                Button("Generate and play offline WAV") {
                    Task { await neural.speak(script) }
                }.disabled(!neural.installed || neural.busy)
            }
            GhostlineNeuralEvidencePanel(evidence: neural.evidence)
            Section("Status") {
                Text(neural.state).font(.footnote)
                Text("Voices are synthetic presets, not actor or character clones. Kyutai PocketTTS weights CC BY 4.0, with separate voice-specific licenses.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.navigationTitle("PocketTTS Offline")
    }
}
