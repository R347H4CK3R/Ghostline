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
    let evidence = GhostlineNeuralAudioEvidence()
    private var engine = KokoroAneManager(variant: .english)

    var voices: [String] {
        switch language {
        case "Mandarin": return ["zf_001","zf_002","zf_003","zf_004","zf_005","zf_006","zf_007","zf_008","zm_009","zm_010"]
        default: return "af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis ef_dora em_alex em_santa ff_siwis hf_alpha hf_beta hm_omega hm_psi if_sara im_nicola jf_alpha jf_gongitsune jf_nezumi jf_tebukuro jm_kumo pf_dora pm_alex pm_santa zf_xiaobei zf_xiaoni zf_xiaoxiao zf_xiaoyi zm_yunjian zm_yunxi zm_yunxia zm_yunyang".split(separator: " ").map(String.init)
        }
    }
    func clearOutput() {
        output = nil
        evidence.reset()
    }
    func changeLanguage(_ value: String) {
        guard !busy else { return }
        language = value
        prepared = false
        clearOutput()
        let variant: KokoroAneVariant
        switch value {
        case "Mandarin": variant = .mandarin
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
        clearOutput()
        let selectedVoice = voiceID
        defer { busy = false }
        do {
            status = "Generating Kokoro audio on device for \(selectedVoice)..."
            let wav = try await engine.synthesize(text: text, voice: selectedVoice)
            output = try evidence.acceptGeneratedWAV(wav, engine: "Kokoro", voiceID: selectedVoice)
            status = "Kokoro produced validated WAV samples for \(selectedVoice); offline isolation and identity remain unverified."
        } catch { status = "Generation failed: \(error.localizedDescription)" }
    }
}

struct KokoroOfflineView: View {
    @StateObject private var studio = KokoroOfflineStudio()
    @State private var script = "Welcome to Ghostline. This is a free offline neural voice."
    private let languages = ["English","Mandarin"]
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
                Text("\(studio.voices.count) published voice IDs for \(studio.language); function is verified only after audio plays on-device.")
                    .font(.footnote).foregroundStyle(.secondary)
                Picker("Voice",selection:$studio.voiceID) {
                    ForEach(studio.voices,id:\.self) { Text($0).tag($0) }
                }
                .disabled(studio.busy)
                .onChange(of: studio.voiceID) { _, _ in studio.clearOutput() }
                TextEditor(text: $script).frame(minHeight:80)
                Button("Generate offline speech") { Task { await studio.generate(script) } }
                    .disabled(studio.busy || !studio.prepared)
            }
            GhostlineNeuralEvidencePanel(evidence: studio.evidence)
            Section("Status") {
                Text(studio.status).font(.footnote)
                Text("Free Kokoro model, Apache-2.0. Voices are synthetic, not authorized celebrity identity clones.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Kokoro Offline Voices")
    }
}
