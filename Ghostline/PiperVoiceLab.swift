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
    // The model configuration determines valid speaker IDs. Milestones are not caps.

    @Published var status = "Download the Piper multispeaker pack before offline verification."
    @Published var busy = false
    @Published var modelReady = false
    @Published var speakerID = 0
    @Published var testedCount = 0
    @Published var uniqueHashes = 0
    @Published var progress = 0
    @Published var batchStart = 0
    @Published var batchSize = 25
    @Published var latestOutput: URL?
    @Published var evidenceFile: URL?
    @Published var cancelRequested = false

    private let registry = PiperRegistry.load()
    private var player: PiperPlayer?
    private var avPlayer: AVAudioPlayer?
    private struct Checkpoint: Codable {
        let modelSHA256: String
        let configSHA256: String
        var decodedPCMHashes: [Int: String]
    }
    private var tested: [Int: String] = [:]
    // Old v2 candidate hashes had no model binding and are deliberately not promoted.
    private let key = "piper.voice.lab.decodedPCM.v3"
    private var modelSHA256: String?
    private var configSHA256: String?
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

    var speakerCount: Int { modelReady ? (configSpeakerCount ?? 0) : 0 }

    init() {
        if FileManager.default.fileExists(atPath: modelURL.path) ||
           FileManager.default.fileExists(atPath: configURL.path) {
            do {
                let fingerprints = try validateInstalledPack()
                modelSHA256 = fingerprints.0
                configSHA256 = fingerprints.1
                modelReady = true
                if let saved = UserDefaults.standard.data(forKey: key),
                   let checkpoint = try? JSONDecoder().decode(Checkpoint.self, from: saved),
                   checkpoint.modelSHA256 == fingerprints.0,
                   checkpoint.configSHA256 == fingerprints.1 {
                    let count = configSpeakerCount ?? 0
                    tested = checkpoint.decodedPCMHashes.filter {
                        $0.key >= 0 && $0.key < count && $0.value.count == 64 &&
                        $0.value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
                    }
                }
            } catch {
                status = "Cached Piper files failed integrity validation; re-download is required: \(error.localizedDescription)"
            }
        }
        updateCounts()
    }

    private func sha256File(_ url: URL) throws -> String {
        let stream = try FileHandle(forReadingFrom: url)
        defer { try? stream.close() }
        var sha = SHA256()
        while let chunk = try stream.read(upToCount: 1_048_576), !chunk.isEmpty {
            sha.update(data: chunk)
        }
        return sha.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func validatePack(at directory: URL) throws -> (String, String) {
        guard let model else {
            throw NSError(domain: "GHOSTLINE", code: 110,
                          userInfo: [NSLocalizedDescriptionKey: "Model registry missing"])
        }
        let weight = directory.appendingPathComponent("model.onnx")
        let config = directory.appendingPathComponent("model.onnx.json")
        try verifyMD5(weight, expected: model.model_md5)
        try verifyMD5(config, expected: model.config_md5)
        guard let data = try? Data(contentsOf: config),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let count = json["num_speakers"] as? Int, count > 0 else {
            throw NSError(domain: "GHOSTLINE", code: 111,
                          userInfo: [NSLocalizedDescriptionKey: "Speaker configuration invalid"])
        }
        return (try sha256File(weight), try sha256File(config))
    }

    private func validateInstalledPack() throws -> (String, String) {
        try validatePack(at: modelDir)
    }

    private func updateCounts() {
        testedCount = tested.count
        uniqueHashes = Set(tested.values).count
    }
    private func persist() {
        if let modelSHA256, let configSHA256,
           let bytes = try? JSONEncoder().encode(Checkpoint(modelSHA256: modelSHA256,
                                                            configSHA256: configSHA256,
                                                            decodedPCMHashes: tested)) {
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
        let fm = FileManager.default
        let parent = modelDir.deletingLastPathComponent()
        let staging = parent.appendingPathComponent("incoming-\(UUID().uuidString)", isDirectory: true)
        let backup = parent.appendingPathComponent("backup-\(UUID().uuidString)", isDirectory: true)
        let priorModelHash = modelSHA256
        let priorConfigHash = configSHA256
        do {
            try fm.createDirectory(at: staging, withIntermediateDirectories: true)
            status = "Downloading \(model.model_bytes / 1_000_000) MB Piper model into temporary storage..."
            try await fetch(model.model_url, to: staging.appendingPathComponent("model.onnx"),
                            md5: model.model_md5)
            status = "Downloading and verifying speaker configuration..."
            try await fetch(model.config_url, to: staging.appendingPathComponent("model.onnx.json"),
                            md5: model.config_md5)
            let fingerprints = try validatePack(at: staging)
            if fm.fileExists(atPath: modelDir.path) {
                try fm.moveItem(at: modelDir, to: backup)
            }
            do {
                try fm.moveItem(at: staging, to: modelDir)
            } catch {
                if fm.fileExists(atPath: backup.path) {
                    try? fm.moveItem(at: backup, to: modelDir)
                }
                throw error
            }
            modelSHA256 = fingerprints.0
            configSHA256 = fingerprints.1
            modelReady = true
            player = nil
            latestOutput = nil
            evidenceFile = nil
            if priorModelHash != fingerprints.0 || priorConfigHash != fingerprints.1 {
                tested.removeAll()
                batchStart = 0
                UserDefaults.standard.removeObject(forKey: key)
                persist()
            }
            if fm.fileExists(atPath: backup.path) { try? fm.removeItem(at: backup) }
            status = "Both model files verified and installed together. Offline speaker tests may begin."
        } catch {
            try? fm.removeItem(at: staging)
            if fm.fileExists(atPath: backup.path) && !fm.fileExists(atPath: modelDir.path) {
                try? fm.moveItem(at: backup, to: modelDir)
            }
            modelReady = (try? validateInstalledPack()) != nil
            status = "Model update failed; any previous intact pack was preserved: \(error.localizedDescription)"
        }
    }

    private func ensurePlayer() throws -> PiperPlayer {
        if let player { return player }
        guard modelReady, let modelSHA256, let configSHA256 else {
            throw NSError(domain: "GHOSTLINE", code: 102,
                          userInfo: [NSLocalizedDescriptionKey: "Verified model must be downloaded first"])
        }
        let current = try validateInstalledPack()
        guard current.0 == modelSHA256, current.1 == configSHA256 else {
            throw NSError(domain: "GHOSTLINE", code: 112,
                          userInfo: [NSLocalizedDescriptionKey: "Installed model changed since device tests"])
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
        try finalizeGeneratedWAV(file)
        let attrs = try FileManager.default.attributesOfItem(atPath: path)
        guard (attrs[.size] as? NSNumber)?.intValue ?? 0 > 1024 else {
            throw NSError(domain: "GHOSTLINE", code: 104,
                          userInfo: [NSLocalizedDescriptionKey: "Empty audio output"])
        }
        return file
    }

    // The pinned piper-objc writer emits a streaming WAV header with placeholder
    // RIFF/data sizes (0x7ffff000) even after closing a saved file. AVFoundation
    // can interpret that as a multi-GB truncated stream. Finalize from the real
    // file length before decoding, playing, hashing, or exporting on iPhone.
    private func finalizeGeneratedWAV(_ url: URL) throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: url.path)
        guard let length = (attrs[.size] as? NSNumber)?.uint64Value,
              length >= 48, length - 8 <= UInt64(UInt32.max),
              (length - 44) % 4 == 0 else {
            throw NSError(domain: "GHOSTLINE", code: 108,
                          userInfo: [NSLocalizedDescriptionKey: "Invalid Piper WAV size"])
        }
        let handle = try FileHandle(forUpdating: url)
        defer { try? handle.close() }
        guard let header = try handle.read(upToCount: 44), header.count == 44,
              header[0..<4].elementsEqual("RIFF".utf8),
              header[8..<12].elementsEqual("WAVE".utf8),
              header[12..<16].elementsEqual("fmt ".utf8),
              header[36..<40].elementsEqual("data".utf8),
              header[20] == 3, header[21] == 0, // IEEE float samples
              header[22] == 1, header[23] == 0, // mono
              header[34] == 32, header[35] == 0 else {
            throw NSError(domain: "GHOSTLINE", code: 109,
                          userInfo: [NSLocalizedDescriptionKey: "Unexpected Piper WAV layout"])
        }
        var riffLength = UInt32(length - 8).littleEndian
        var payloadLength = UInt32(length - 44).littleEndian
        try handle.seek(toOffset: 4)
        try handle.write(contentsOf: withUnsafeBytes(of: &riffLength) { Data($0) })
        try handle.seek(toOffset: 40)
        try handle.write(contentsOf: withUnsafeBytes(of: &payloadLength) { Data($0) })
    }

    func preview(_ words: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        guard speakerID >= 0 && speakerID < speakerCount else {
            status = "Speaker ID must be within the downloaded model's configuration."
            return
        }
        do {
            status = "Generating speaker \(speakerID) with local Piper..."
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
            status = "Speaker \(speakerID) generated decodable WAV. Listen to confirm distinctness."
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
        guard !busy, let model, !tested.isEmpty,
              let modelSHA256, let configSHA256 else { return }
        do {
            let current = try validateInstalledPack()
            guard current.0 == modelSHA256, current.1 == configSHA256 else {
                status = "Evidence withheld: cached model or configuration has changed."
                evidenceFile = nil
                return
            }
        } catch {
            status = "Evidence withheld: model integrity check failed: \(error.localizedDescription)"
            evidenceFile = nil
            return
        }
        let hashes = Dictionary(uniqueKeysWithValues:
            tested.map { (String($0.key), $0.value) })
        let report: [String: Any] = [
            "schema_version": 2,
            "test_type": "piper_ios_decoded_pcm",
            "model_sha256": modelSHA256,
            "config_sha256": configSHA256,
            "device_category": UIDevice.current.model,
            "ios_version": UIDevice.current.systemVersion,
            "model_id": model.model_id,
            "model_md5": model.model_md5 ?? "",
            "config_md5": model.config_md5 ?? "",
            "catalog_declared_speakers": model.declared_speakers,
            "model_config_speakers": speakerCount,
            "speaker_count_has_no_app_cap": true,
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
            status = "Export ready: decoded PCM candidate evidence only. Human listening, rights, and airplane-mode verification remain outstanding."
        } catch {
            status = "Evidence export failed: \(error.localizedDescription)"
        }
    }

    // An incremental range prevents long, uninterruptible validation sessions.
    // A batch size is a per-run throttle, never a library or speaker-count cap.
    func verifyBatch() async {
        guard !busy else { return }
        let count = speakerCount
        guard modelReady, count > 0 else {
            status = "Download the model and its speaker configuration first."
            return
        }
        guard batchStart >= 0, batchStart < count, batchSize > 0 else {
            status = "Choose a valid start ID and positive batch size. Available IDs: 0–\(count - 1)."
            return
        }
        let end = min(count, batchStart + min(batchSize, count))
        let start = batchStart
        busy = true
        cancelRequested = false
        defer { busy = false }
        do {
            _ = try ensurePlayer()
            for id in start..<end where tested[id] == nil {
                if cancelRequested || Task.isCancelled { break }
                status = "Decoding speaker \(id) of \(count - 1), range \(start)–\(end - 1)."
                let wav = try await synthesize(batchPhrase, speaker: id)
                defer { try? FileManager.default.removeItem(at: wav) }
                let audio = try AVAudioPlayer(contentsOf: wav)
                guard audio.duration > 0.2 else {
                    status = "Speaker \(id) generated invalid WAV. Stopped at this ID."
                    persist()
                    return
                }
                let hash = try decodedPCMHash(wav)
                tested[id] = hash
                evidenceFile = nil
                progress = id + 1
                if id % 10 == 0 { persist(); await Task.yield() }
            }
            batchStart = end < count ? end : 0
            persist()
            status = "Decoded \(testedCount) of \(count) model speaker IDs; \(uniqueHashes) different non-silent PCM streams. Identity and airplane-mode tests still needed."
        } catch {
            persist()
            status = "Batch halted: \(error.localizedDescription). Saved \(testedCount) decoded PCM results."
        }
    }

    func clearDownloadedPack() {
        guard !busy else { return }
        try? FileManager.default.removeItem(at: modelDir)
        modelReady = false
        player = nil
        avPlayer = nil
        modelSHA256 = nil
        configSHA256 = nil
        tested.removeAll()
        batchStart = 0
        latestOutput = nil
        evidenceFile = nil
        UserDefaults.standard.removeObject(forKey: key)
        updateCounts()
        status = "Local Piper model and its device-test records cleared."
    }
}

struct PiperVoiceLabView: View {
    @StateObject private var lab = PiperVoiceLab()
    @State private var phrase = "Welcome to Ghostline. This voice is generated offline."

    var body: some View {
        Form {
            Section("Included open-licensed synthetic voices") {
                NavigationLink("Browse included Piper packs • UNVERIFIED") {
                    GhostlineIncludedPiperView()
                }
                Text("The current test IPA contains four source-pinned models. This is not a library limit.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Piper LibriTTS-R • expandable speaker test") {
                Text("English • approximately 81 MB model download")
                Text("The model's own config determines available IDs, not a 500-voice app cap. Registry counts may differ from the installed model.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button(lab.modelReady ? "Model downloaded" : "Download free model") {
                    Task { await lab.downloadModel() }
                }.disabled(lab.busy || lab.modelReady)
                Text("Model config speaker slots: \(lab.speakerCount). None is an identity-verified voice simply because it has an ID.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Source: rhasspy/piper-voices. Review each model's MODEL_CARD and license before redistributing. Piper software is GPL-licensed.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Generate local audio") {
                Picker("Speaker ID", selection: $lab.speakerID) {
                    ForEach(0..<max(1, lab.speakerCount), id: \.self) {
                        Text("Speaker \($0)").tag($0)
                    }
                }.disabled(lab.busy || !lab.modelReady || lab.speakerCount == 0)
                TextEditor(text: $phrase).frame(minHeight: 75)
                Button("Generate and play WAV") {
                    Task { await lab.preview(phrase) }
                }.disabled(lab.busy || !lab.modelReady || lab.speakerCount == 0)
                if let file = lab.latestOutput {
                    ShareLink(item: file) {
                        Label("Export generated WAV", systemImage: "square.and.arrow.up")
                    }
                }
            }
            Section("Incremental on-device candidate checks") {
                Text("\(lab.testedCount) / \(lab.speakerCount) decoded speaker IDs")
                Text("\(lab.uniqueHashes) unique non-silent decoded PCM hashes (not verified identities)")
                ProgressView(value: Double(lab.testedCount), total: Double(max(1, lab.speakerCount)))
                Stepper("Start ID: \(lab.batchStart)", value: $lab.batchStart,
                        in: 0...max(0, lab.speakerCount - 1))
                    .disabled(lab.busy || lab.speakerCount == 0)
                Stepper("IDs per run: \(lab.batchSize)", value: $lab.batchSize,
                        in: 1...max(1, lab.speakerCount))
                    .disabled(lab.busy || lab.speakerCount == 0)
                Button("Test selected speaker range") {
                    Task { await lab.verifyBatch() }
                }.disabled(!lab.modelReady || lab.busy || lab.speakerCount == 0)
                if lab.busy {
                    Button("Stop after current speaker") { lab.cancelRequested = true }
                }
                Button("Prepare device evidence JSON") { lab.prepareEvidence() }
                    .disabled(lab.busy || lab.testedCount == 0)
                if let file = lab.evidenceFile {
                    ShareLink(item: file) {
                        Label("Share candidate test evidence", systemImage: "square.and.arrow.up")
                    }
                }
                Text("Hashes establish different decoded waveforms, not distinct speakers or identities. The evidence never self-certifies listening or airplane mode. Run actual offline checks and review each sound on the target iPhone.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Status") {
                Text(lab.status).font(.footnote)
                Button("Delete downloaded pack and tests", role: .destructive) {
                    lab.clearDownloadedPack()
                }.disabled(lab.busy)
            }
        }
        .navigationTitle("Piper Speaker Lab")
    }
}
