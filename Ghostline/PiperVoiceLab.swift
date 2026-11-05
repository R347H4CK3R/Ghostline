import SwiftUI
import AVFoundation
import CryptoKit
import piper_player

// Model and speaker metadata are bundled for browsing; no candidate is
// considered device-verified until it produces independently decoded WAV audio.
private struct PiperRegistry: Decodable {
    struct Model: Decodable {
        let model_id: String
        let model_bytes: Int
        let declared_speakers: Int
        let model_url: String
        let config_url: String
        let model_md5: String?
        let config_md5: String?
    }
    let model_count: Int
    let speaker_candidate_count: Int
    let models: [Model]

    static func load() -> PiperRegistry? {
        guard let file = Bundle.main.url(forResource: "piper-candidates", withExtension: "json"),
              let bytes = try? Data(contentsOf: file)
        else { return nil }
        return try? JSONDecoder().decode(PiperRegistry.self, from: bytes)
    }
}

@MainActor
final class PiperVoiceLab: ObservableObject {
    static let featuredModelID = "en_US-libritts_r-medium"
    static let targetCount = 500

    @Published var status = "Download the Piper multispeaker pack before offline verification."
    @Published var busy = false
    @Published var modelReady = false
    @Published var speakerID = 0
    @Published var testedCount = 0
    @Published var uniqueHashes = 0
    @Published var progress = 0
    @Published var latestOutput: URL?
    @Published var evidenceFile: URL?
    @Published var cancelRequested = false

    private let registry = PiperRegistry.load()
    private var player: PiperPlayer?
    private var avPlayer: AVAudioPlayer?
    private var tested: [Int: String] = [:]
    private let key = "piper.voice.lab.decodedPCM.v2"
    private let batchPhrase = "A quick silver fox crossed the quiet valley."
    private var model: PiperRegistry.Model? {
        registry?.models.first { $0.model_id == Self.featuredModelID }
    }
    private var modelDir: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("PiperModels", isDirectory: true)
            .appendingPathComponent(Self.featuredModelID, isDirectory: true)
    }
    private var modelURL: URL { modelDir.appendingPathComponent("model.onnx") }
    private var configURL: URL { modelDir.appendingPathComponent("model.onnx.json") }

    // Piper model config is authoritative. The upstream index currently
    // reports 2,306 for LibriTTS-R, but the actual model config has 904.
    private var configSpeakerCount: Int? {
        guard let data = try? Data(contentsOf: configURL),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let count = json["num_speakers"] as? Int, count > 0 else { return nil }
        return count
    }

    init() {
        if let saved = UserDefaults.standard.data(forKey: key),
           let v = try? JSONDecoder().decode([Int: String].self, from: saved) {
            tested = v
            updateCounts()
        }
        modelReady = FileManager.default.fileExists(atPath: modelURL.path) &&
            FileManager.default.fileExists(atPath: configURL.path)
    }

    private func updateCounts() {
        testedCount = tested.count
        uniqueHashes = Set(tested.values).count
    }
    private func persist() {
        if let bytes = try? JSONEncoder().encode(tested) {
            UserDefaults.standard.set(bytes, forKey: key)
        }
        updateCounts()
    }

    private func verifyMD5(_ file: URL, expected: String?) throws {
        guard let expected, expected.count == 32 else {
            throw NSError(domain: "GHOSTLINE", code: 100,
                          userInfo: [NSLocalizedDescriptionKey: "Missing model checksum"])
        }
        let data = try Data(contentsOf: file, options: .mappedIfSafe)
        let digest = Insecure.MD5.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard digest.lowercased() == expected.lowercased() else {
            throw NSError(domain: "GHOSTLINE", code: 101,
                          userInfo: [NSLocalizedDescriptionKey: "Model checksum mismatch"])
        }
    }

    private func fetch(_ urlString: String, to destination: URL, md5: String?) async throws {
        guard let url = URL(string: urlString),
              url.scheme == "https", url.host == "huggingface.co"
        else { throw URLError(.badURL) }
        let (temporary, response) = try await URLSession.shared.download(from: url)
        guard let response = response as? HTTPURLResponse, (200...299).contains(response.statusCode)
        else { throw URLError(.badServerResponse) }
        try verifyMD5(temporary, expected: md5)
        if FileManager.default.fileExists(atPath: destination.path) {
            try FileManager.default.removeItem(at: destination)
        }
        try FileManager.default.moveItem(at: temporary, to: destination)
    }

    func downloadModel() async {
        guard !busy, let model else {
            status = "Voice candidate catalog not found in IPA."
            return
        }
        busy = true
        defer { busy = false }
        do {
            try FileManager.default.createDirectory(at: modelDir, withIntermediateDirectories: true)
            status = "Downloading \(model.model_bytes / 1_000_000) MB Piper model (once)..."
            try await fetch(model.model_url, to: modelURL, md5: model.model_md5)
            status = "Downloading speaker configuration..."
            try await fetch(model.config_url, to: configURL, md5: model.config_md5)
            modelReady = true
            player = nil
            status = "Verified model files downloaded. Speech can now be generated offline."
        } catch {
            modelReady = false
            status = "Model download/integrity check failed: \(error.localizedDescription)"
        }
    }

    private func ensurePlayer() throws -> PiperPlayer {
        if let player { return player }
        guard modelReady else {
            throw NSError(domain: "GHOSTLINE", code: 102,
                          userInfo: [NSLocalizedDescriptionKey: "Model must be downloaded first"])
        }
        let created = try PiperPlayer(params: .init(modelPath: modelURL.path,
                                                   configPath: configURL.path))
        player = created
        return created
    }

    private func synthesize(_ words: String, speaker: Int) async throws -> URL {
        let p = try ensurePlayer()
        // Escape user text before passing it to Piper's SSML parser.
        let safe = words.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
        guard let path = await p.synthesizeSSMLToFile(ssml: "<speak>\(safe)</speak>",
                                                    speakerId: Int32(speaker))
        else {
            throw NSError(domain: "GHOSTLINE", code: 103,
                          userInfo: [NSLocalizedDescriptionKey: "Speech engine returned no audio"])
        }
        let file = URL(fileURLWithPath: path)
        let attrs = try FileManager.default.attributesOfItem(atPath: path)
        guard (attrs[.size] as? NSNumber)?.intValue ?? 0 > 1024 else {
            throw NSError(domain: "GHOSTLINE", code: 104,
                          userInfo: [NSLocalizedDescriptionKey: "Empty audio output"])
        }
        return file
    }

    func preview(_ words: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            status = "Generating \(PiperVoiceNames.label(for: speakerID)) with local Piper..."
            let wav = try await synthesize(words, speaker: speakerID)
            let audio = try AVAudioPlayer(contentsOf: wav)
            guard audio.duration > 0.2, audio.prepareToPlay() else {
                status = "Output failed WAV decoding."
                return
            }
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            avPlayer = audio
            latestOutput = wav
            _ = audio.play()
            status = "\(PiperVoiceNames.label(for: speakerID)) generated decodable WAV (Piper ID \(speakerID)). Listen to confirm distinctness."
        } catch { status = "Piper generation failed: \(error.localizedDescription)" }
    }


    // Hash decoded frames, not WAV headers or filesystem metadata.
    // Different PCM hashes prove different waveforms, NOT perceptually distinct voices.
    private func decodedPCMHash(_ wav: URL) throws -> String {
        let source = try AVAudioFile(forReading: wav)
        guard source.length > 0, source.length < 5_000_000,
              let pcm = AVAudioPCMBuffer(pcmFormat: source.processingFormat,
                                         frameCapacity: AVAudioFrameCount(source.length)) else {
            throw NSError(domain: "GHOSTLINE", code: 105,
                          userInfo: [NSLocalizedDescriptionKey: "Invalid WAV frame count"])
        }
        try source.read(into: pcm)
        guard pcm.frameLength > 0, let channels = pcm.floatChannelData else {
            throw NSError(domain: "GHOSTLINE", code: 106,
                          userInfo: [NSLocalizedDescriptionKey: "WAV has no decoded PCM"])
        }
        var hasher = SHA256()
        var peak: Float = 0
        let frameCount = Int(pcm.frameLength)
        for channel in 0..<Int(pcm.format.channelCount) {
            let samples = channels[channel]
            hasher.update(data: Data(bytes: samples,
                                     count: frameCount * MemoryLayout<Float>.stride))
            for index in stride(from: 0, to: frameCount, by: max(1, frameCount / 8192)) {
                peak = max(peak, abs(samples[index]))
            }
        }
        guard peak > 0.0001 else {
            throw NSError(domain: "GHOSTLINE", code: 107,
                          userInfo: [NSLocalizedDescriptionKey: "Audio is effectively silent"])
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    // Export device test evidence without unique device identifiers.
    // The JSON does not certify airplane mode or listening distinctness.
    func prepareEvidence() {
        guard !busy, let model, !tested.isEmpty else { return }
        let hashes = Dictionary(uniqueKeysWithValues:
            tested.map { (String($0.key), $0.value) })
        let report: [String: Any] = [
            "schema_version": 1,
            "test_type": "piper_ios_decoded_pcm",
            "device_category": UIDevice.current.model,
            "ios_version": UIDevice.current.systemVersion,
            "model_id": model.model_id,
            "model_md5": model.model_md5 ?? "",
            "config_md5": model.config_md5 ?? "",
            "catalog_declared_speakers": model.declared_speakers,
            "model_config_speakers": configSpeakerCount ?? 0,
            "sample_phrase": batchPhrase,
            "decoded_speaker_count": testedCount,
            "unique_decoded_pcm_hashes": uniqueHashes,
            "speaker_pcm_sha256": hashes,
            "airplane_mode_confirmed": false,
            "distinct_voice_listening_confirmed": false,
            "generated_utc": ISO8601DateFormatter().string(from: Date())
        ]
        do {
            let bytes = try JSONSerialization.data(withJSONObject: report,
                                                   options: [.prettyPrinted, .sortedKeys])
            let file = FileManager.default.temporaryDirectory
                .appendingPathComponent("ghostline-device-check-\(UUID().uuidString).json")
            try bytes.write(to: file, options: .atomic)
            evidenceFile = file
            status = "Export ready: decoded PCM evidence only. Confirm airplane mode and listen to voices before claiming 500 verified voices."
        } catch {
            status = "Evidence export failed: \(error.localizedDescription)"
        }
    }

    func verifyBatch() async {
        guard !busy else { return }
        guard (configSpeakerCount ?? 0) >= Self.targetCount else {
            status = "The installed model config does not support 500 speaker IDs."
            return
        }
        busy = true
        cancelRequested = false
        defer { busy = false }
        do {
            _ = try ensurePlayer()
            let sample = batchPhrase
            for id in 0..<Self.targetCount where tested[id] == nil {
                if cancelRequested || Task.isCancelled { break }
                status = "Device audio-check \(id + 1) of \(Self.targetCount)."
                let wav = try await synthesize(sample, speaker: id)
                let audio = try AVAudioPlayer(contentsOf: wav)
                guard audio.duration > 0.2 else {
                    status = "Speaker \(id) generated invalid WAV. Verification stopped."
                    break
                }
                let hash = try decodedPCMHash(wav)
                tested[id] = hash
                evidenceFile = nil  // Never share a stale report after new tests.
                try? FileManager.default.removeItem(at: wav)
                progress = id + 1
                if id % 10 == 0 { persist(); await Task.yield() }
            }
            persist()
            status = "Decoded \(testedCount) / 500 speaker IDs; \(uniqueHashes) distinct non-silent PCM streams. Airplane-mode and listening checks remain necessary."
        } catch {
            persist()
            status = "Batch halted: \(error.localizedDescription). Saved \(testedCount) decoded samples."
        }
    }

    func clearDownloadedPack() {
        guard !busy else { return }
        try? FileManager.default.removeItem(at: modelDir)
        modelReady = false
        player = nil
        tested = [:]
        evidenceFile = nil
        persist()
        status = "Local Piper model and its device-test records cleared."
    }
}


// These are fictional UI aliases, not verified identities, voice qualities,
// or the names of LibriTTS speakers. Keep the mapping stable across releases.
private enum PiperVoiceNames {
    static let given = [
        "Avery", "Blair", "Casey", "Dakota", "Ellis",
        "Finley", "Harper", "Indigo", "Jules", "Kai",
        "Lane", "Morgan", "Noel", "Oakley", "Parker",
        "Quinn", "Reese", "Rowan", "Sage", "Taylor",
        "Uma", "Val", "Wren", "Yael", "Zuri"
    ]
    static let nature = [
        "Cedar", "Willow", "Juniper", "River", "Meadow",
        "Aspen", "Clover", "Orchid", "Maple", "Briar",
        "Fern", "Brook", "Laurel", "Dawn", "Sky",
        "Hazel", "Dune", "Ember", "Marigold", "Grove"
    ]
    static func label(for id: Int) -> String {
        guard id >= 0 && id < 500 else { return "Voice ID \(id)" }
        return "\(given[id / nature.count]) \(nature[id % nature.count])"
    }
}

struct PiperVoiceLabView: View {
    @StateObject private var lab = PiperVoiceLab()
    @State private var phrase = "Welcome to Ghostline. This voice is generated offline."
    var body: some View {
        Form {
            Section("One model, 500 speaker candidates") {
                Text("Piper LibriTTS-R medium • English • approximately 79 MB")
                Text("Open-source multispeaker voice model. These 500 candidate IDs are not yet 500 independently verified or distinct voices.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button(lab.modelReady ? "Model downloaded" : "Download free voice pack") {
                    Task { await lab.downloadModel() }
                }.disabled(lab.busy || lab.modelReady)
                Text("Source: rhasspy/piper-voices. Dataset: CC BY 4.0. GHOSTLINE uses the GPL-licensed Piper software; redistribution must comply with all applicable licenses.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Generate local audio") {
                Picker("Voice name", selection: $lab.speakerID) {
                    ForEach(0..<500, id:\.self) { Text(PiperVoiceNames.label(for: $0)).tag($0) }
                }
                Text("Piper voice ID: \(lab.speakerID) • Names are fictional labels, not actual speaker identities.")
                    .font(.caption).foregroundStyle(.secondary)
                TextEditor(text: $phrase).frame(minHeight: 75)
                Button("Speak selected voice") { Task { await lab.preview(phrase) } }
                    .disabled(!lab.modelReady || lab.busy)
                if let file = lab.latestOutput {
                    ShareLink(item: file) { Label("Export WAV", systemImage: "square.and.arrow.up") }
                }
            }
            Section("Offline device-verification run") {
                Text("\(lab.testedCount) / 500 speaker IDs generated decodable WAV")
                Text("\(lab.uniqueHashes) different decoded PCM hashes (not verified voice identities)")
                ProgressView(value: Double(lab.testedCount), total: 500)
                Button("Test remaining speakers automatically") {
                    Task { await lab.verifyBatch() }
                }.disabled(!lab.modelReady || lab.busy)
                if lab.busy {
                    Button("Stop after current voice") { lab.cancelRequested = true }
                }
                Button("Prepare device evidence JSON") { lab.prepareEvidence() }
                    .disabled(lab.busy || lab.testedCount == 0)
                if let file = lab.evidenceFile {
                    ShareLink(item: file) { Label("Share device test record", systemImage: "square.and.arrow.up") }
                }
                Text("Audio decoding verifies technical generation, not perceptual quality or identity. The export does not claim airplane-mode validation. The 500-voice target is NOT complete until listening and offline device behavior are confirmed.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Status") {
                Text(lab.status).font(.footnote)
                Button("Delete model and clear tests", role: .destructive) { lab.clearDownloadedPack() }
                    .disabled(lab.busy)
            }
        }
        .navigationTitle("Piper 500 Voice Lab")
    }
}
