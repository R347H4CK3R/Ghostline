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
    private let idleRetention: Duration
    private var idleRelease: Task<Void, Never>?
    private var requestGeneration = UUID()
    private var inUse = false
    private var releaseRequested = false
    init(steps: Int = 32, seed: UInt64 = 0, idleRetention: Duration = .seconds(60)) {
        self.steps = steps; self.seed = seed; self.idleRetention = idleRetention
    }
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
        idleRelease?.cancel(); idleRelease = nil
        requestGeneration = UUID(); inUse = true; releaseRequested = false
        if loadedURL == localBundle, engine != nil { return }
        engine = nil; loadedURL = nil
        try validateBundle(localBundle)
        engine = try await F5TTSModel.fromBundle(localBundle)
        loadedURL = localBundle
    }
    func speak(text: String, referenceAudio: URL, referenceText: String, destination: URL, pauseSeconds: Double = 0.12, preserveIncomplete: Bool = false, progress: @escaping @Sendable (Int, Int) -> Void = { _, _ in }) async throws {
        guard let engine, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !referenceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw NSError(domain: "VoiceMatrix.F5", code: 1, userInfo: [NSLocalizedDescriptionKey: "Load a local engine and character reference first."])
        }
        try Task.checkCancellation()
        let options = try F5TTSSynthesisOptions(steps: steps, seed: seed)
        let input = try AVAudioFile(forReading: referenceAudio)
        let seconds = Double(input.length) / input.fileFormat.sampleRate
        let chunks = try F5SpeechChunks.plan(text: text, referenceText: referenceText, referenceSeconds: seconds)
        guard pauseSeconds.isFinite, (0...1).contains(pauseSeconds),
              let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1) else {
            throw NSError(domain: "VoiceMatrix.F5", code: 2)
        }
        var completed = false
        var writer: AVAudioFile? = try AVAudioFile(forWriting: destination, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        defer { writer = nil; if !completed && !preserveIncomplete { try? FileManager.default.removeItem(at: destination) } }
        var writtenFrames = 0
        func append(_ samples: [Float]) throws {
            try Task.checkCancellation()
            guard writtenFrames + samples.count <= Int(F5SpeechChunks.maximumJobSeconds * 24000),
                  let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
                  let channel = buffer.floatChannelData?[0] else { throw F5ChunkError.jobTooLong }
            buffer.frameLength = AVAudioFrameCount(samples.count)
            let peak = samples.reduce(Float(0)) { max($0, abs($1)) }
            let gain = min(Float(1), 0.98 / max(peak, 0.000001))
            for (index, value) in samples.enumerated() { channel[index] = value * gain }
            try writer?.write(from: buffer)
            writtenFrames += samples.count
        }
        for (index, chunk) in chunks.enumerated() {
            try Task.checkCancellation()
            let tokens = try engine.tokenizer.encode(F5SpeechChunks.normalizedReference(referenceText) + chunk)
            try F5SpeechChunks.validateTokenCount(tokens.count)
            progress(index + 1, chunks.count)
            let clip = try await engine.generate(text: chunk, referenceAudio: referenceAudio, referenceText: referenceText, options: options)
            try Task.checkCancellation()
            guard clip.count >= 2400, clip.allSatisfy({ $0.isFinite }),
                  clip.reduce(0.0, { $0 + Double($1) * Double($1) }) / Double(clip.count) > 1e-8 else {
                throw NSError(domain: "VoiceMatrix.F5", code: 2, userInfo: [NSLocalizedDescriptionKey: "One part of the message did not produce usable speech. Try another reference."])
            }
            if index > 0, pauseSeconds > 0 { try append([Float](repeating: 0, count: Int(pauseSeconds * 24000))) }
            try append(clip)
        }
        try Task.checkCancellation()
        completed = true
    }
    // A successful plain-WAV request may keep only the shared model briefly.
    // References are reopened and validated for every request; no trust is persisted.
    func finishRequest(keepWarm: Bool) {
        inUse = false
        guard keepWarm, !Task.isCancelled, !releaseRequested, engine != nil else { unload(); return }
        idleRelease?.cancel()
        let token = requestGeneration, delay = idleRetention
        idleRelease = Task { [weak self] in
            do { try await Task.sleep(for: delay) } catch { return }
            await self?.expire(token)
        }
    }
    func requestRelease() {
        releaseRequested = true
        // Never invalidate the runtime in the middle of an awaited generation.
        if !inUse { unload() }
    }
    private func expire(_ token: UUID) {
        guard token == requestGeneration, !inUse else { return }
        unload()
    }
    func unload() {
        idleRelease?.cancel(); idleRelease = nil
        requestGeneration = UUID(); inUse = false; releaseRequested = false
        engine?.unload(); engine = nil; loadedURL = nil
    }
}
