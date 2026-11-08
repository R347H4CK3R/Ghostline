import Foundation
import AVFoundation
import F5TTS
import CryptoKit

// Shared local F5 runtime. Character references are imported separately; no stock fallback.
actor F5ReferenceEngine {
    private var engine: F5TTSModel?
    private var loadedURL: URL?
    private let steps: Int
    private let seed: UInt64
    init(steps: Int = 32, seed: UInt64 = 347) { self.steps = steps; self.seed = seed }
    private struct Proof: Decodable {
        struct File: Decodable { let path, sha256: String; let size: Int }
        let schemaVersion: Int
        let engine, runtimeRevision: String
        let files: [File]
    }
    private func validateBundle(_ root: URL) throws {
        let manifest = try Data(contentsOf: root.appendingPathComponent("voicematrix-engine.json"))
        guard manifest.count <= 65536 else { throw NSError(domain: "VoiceMatrix.F5", code: 3) }
        let proof = try JSONDecoder().decode(Proof.self, from: manifest)
        let required = Set(["README.md", "config.json", "model.safetensors", "vocos.safetensors", "vocos_config.yaml", "vocab.txt", "pinyin_lexicon.tsv"])
        guard proof.schemaVersion == 1, proof.engine == "F5TTS_v1_Base",
              proof.runtimeRevision == "a57702e6f523fa36ac5532d2bdc5f35f701a052c",
              proof.files.count == required.count, Set(proof.files.map(\.path)) == required else {
            throw NSError(domain: "VoiceMatrix.F5", code: 3, userInfo: [NSLocalizedDescriptionKey: "The shared speech engine is incomplete or incompatible."])
        }
        for file in proof.files {
            try Task.checkCancellation()
            let url = root.appendingPathComponent(file.path)
            let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == file.size,
                  file.size > 0, file.size < 1_000_000_000 else { throw NSError(domain: "VoiceMatrix.F5", code: 3) }
            let handle = try FileHandle(forReadingFrom: url)
            defer { try? handle.close() }
            var hash = SHA256()
            while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty {
                try Task.checkCancellation(); hash.update(data: data)
            }
            guard hash.finalize().map({ String(format: "%02x", $0) }).joined() == file.sha256 else {
                throw NSError(domain: "VoiceMatrix.F5", code: 3, userInfo: [NSLocalizedDescriptionKey: "The shared speech engine failed its integrity check. Reinstall a complete build."])
            }
        }
        let config = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("config.json"))) as? [String: Any]
        let files = config?["files"] as? [String: String]
        guard config?["model_name"] as? String == "F5TTS_v1_Base",
              files?["model"] == "model.safetensors", files?["vocoder"] == "vocos.safetensors",
              files?["vocoder_config"] == "vocos_config.yaml", files?["vocab"] == "vocab.txt",
              files?["pinyin_lexicon"] == "pinyin_lexicon.tsv" else { throw NSError(domain: "VoiceMatrix.F5", code: 3) }
    }
    func load(localBundle: URL) async throws {
        try Task.checkCancellation()
        if loadedURL == localBundle, engine != nil { return }
        engine = nil; loadedURL = nil
        try validateBundle(localBundle)
        engine = try await F5TTSModel.fromBundle(localBundle)
        loadedURL = localBundle
    }
    func speak(text: String, referenceAudio: URL, referenceText: String, destination: URL) async throws {
        guard let engine, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !referenceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw NSError(domain: "VoiceMatrix.F5", code: 1, userInfo: [NSLocalizedDescriptionKey: "Load a local engine and character reference first."])
        }
        try Task.checkCancellation()
        let options = try F5TTSSynthesisOptions(steps: steps, seed: seed)
        let samples = try await engine.generate(text: text, referenceAudio: referenceAudio, referenceText: referenceText, options: options)
        try Task.checkCancellation()
        guard samples.count >= 2400, samples.allSatisfy({ $0.isFinite }),
              samples.reduce(0.0, { $0 + Double($1) * Double($1) }) / Double(samples.count) > 1e-8,
              let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let channel = buffer.floatChannelData?[0] else {
            throw NSError(domain: "VoiceMatrix.F5", code: 2, userInfo: [NSLocalizedDescriptionKey: "The voice did not produce usable speech."])
        }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        let gain = min(1, 0.98 / max(samples.map { abs($0) }.max() ?? 0, 0.000001))
        for (index, value) in samples.enumerated() { channel[index] = value * gain }
        let writer = try AVAudioFile(forWriting: destination, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        try writer.write(from: buffer)
    }
    func unload() { engine?.unload(); engine = nil; loadedURL = nil }
}

