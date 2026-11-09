import Foundation
import CryptoKit
import AVFoundation
import F5TTS

struct CheckFailure: Error { let message: String }
func expect(_ value: Bool, _ message: String) throws { if !value { throw CheckFailure(message: message) } }

func until(_ message: String, _ predicate: () async -> Bool) async throws {
    let deadline = ProcessInfo.processInfo.systemUptime + 4
    while !(await predicate()) {
        try expect(ProcessInfo.processInfo.systemUptime < deadline, message)
        try await Task.sleep(for: .milliseconds(10))
    }
}
@main struct SpeechWarmChecks {
    static func main() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let names = ["README.md", "config.json", "model.safetensors", "vocos.safetensors", "vocos_config.yaml", "vocab.txt", "pinyin_lexicon.tsv"]
        let config: [String: Any] = ["model_name":"F5TTS_v1_Base", "files":["model":"model.safetensors", "vocoder":"vocos.safetensors", "vocoder_config":"vocos_config.yaml", "vocab":"vocab.txt", "pinyin_lexicon":"pinyin_lexicon.tsv"]]
        var records: [[String: Any]] = []
        for name in names {
            let data = name == "config.json" ? try JSONSerialization.data(withJSONObject: config) : Data("fixture".utf8)
            try data.write(to: root.appendingPathComponent(name))
            records.append(["path":name, "size":data.count, "sha256":SHA256.hash(data: data).map { String(format:"%02x", $0) }.joined()])
        }
        let proof: [String: Any] = ["schemaVersion":1, "engine":"F5TTS_v1_Base", "runtimeRevision":"a57702e6f523fa36ac5532d2bdc5f35f701a052c", "files":records]
        try JSONSerialization.data(withJSONObject: proof).write(to: root.appendingPathComponent("voicematrix-engine.json"))
        let engine = F5ReferenceEngine(idleRetention: .seconds(1))
        try await engine.load(localBundle: root)
        await engine.finishRequest(keepWarm: true)
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == 1, "A second request must reuse the validated loaded engine")
        await engine.finishRequest(keepWarm: true)
        try await until("Idle release did not run before the deadline") { F5TTSModel.unloads == 1 }
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == 2, "Idle expiry must release the engine")
        await engine.finishRequest(keepWarm: true)
        try await engine.load(localBundle: root)
        try await Task.sleep(for: .milliseconds(1200))
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == 2, "A stale idle timer must not release a newer active request")
        let before = F5TTSModel.unloads
        await engine.requestRelease()
        try expect(F5TTSModel.unloads == before, "Memory pressure must not unload a model while in use")
        await engine.finishRequest(keepWarm: true)
        try expect(F5TTSModel.unloads == before + 1, "Deferred memory-pressure release must win over retention")
        try await engine.load(localBundle: root)
        await engine.finishRequest(keepWarm: false)
        let released = F5TTSModel.unloads
        await engine.requestRelease()
        try expect(F5TTSModel.unloads == released, "Repeated release must be harmless")
        try await engine.load(localBundle: root)
        await engine.finishRequest(keepWarm: true)
        await engine.requestRelease()
        try expect(F5TTSModel.unloads == released + 1, "An idle model must release immediately on background or memory pressure")
        // Pause actual adapter awaits to exercise actor reentrancy without Metal.
        await F5TTSModel.gate.configure(load: true)
        let loading = Task { try await engine.load(localBundle: root) }
        try await until("Loader did not reach suspension") { await F5TTSModel.gate.loadEntered }
        let loadingUnloads = F5TTSModel.unloads
        await engine.requestRelease()
        try expect(F5TTSModel.unloads == loadingUnloads, "Pressure must defer during model loading")
        await F5TTSModel.gate.resumeLoad()
        try await loading.value
        await engine.finishRequest(keepWarm: true)
        try expect(F5TTSModel.unloads == loadingUnloads + 1, "Pressure during load must prevent retention")

        let reference = root.appendingPathComponent("reference.wav")
        let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1)!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 24000)!
        buffer.frameLength = 24000
        for i in 0..<24000 { buffer.floatChannelData![0][i] = 0.1 * sin(Float(i) * 0.1) }
        do {
            let writer = try AVAudioFile(forWriting: reference, settings: [AVFormatIDKey:Int(kAudioFormatLinearPCM), AVSampleRateKey:24000.0, AVNumberOfChannelsKey:1, AVLinearPCMBitDepthKey:16, AVLinearPCMIsFloatKey:false])
            try writer.write(from: buffer)
        }
        let destination = root.appendingPathComponent("output.wav")
        await F5TTSModel.gate.configure(generation: true)
        try await engine.load(localBundle: root)
        let generating = Task { try await engine.speak(text: "Hello world.", referenceAudio: reference, referenceText: "This is a reference recording.", destination: destination) }
        try await until("Generation did not reach suspension") { await F5TTSModel.gate.generationEntered }
        let generatingUnloads = F5TTSModel.unloads
        await engine.requestRelease()
        try expect(F5TTSModel.unloads == generatingUnloads, "Pressure must defer during generation")
        await F5TTSModel.gate.resumeGeneration()
        try await generating.value
        try expect(FileManager.default.fileExists(atPath: destination.path), "A release request must not interrupt successful speech")
        await engine.finishRequest(keepWarm: true)
        try expect(F5TTSModel.unloads == generatingUnloads + 1, "Pressure during generation must prevent retention")
        try FileManager.default.removeItem(at: destination)

        await F5TTSModel.gate.configure(generation: true)
        try await engine.load(localBundle: root)
        let cancelled = Task {
            do {
                try await engine.speak(text: "Hello world.", referenceAudio: reference, referenceText: "This is a reference recording.", destination: destination)
                await engine.finishRequest(keepWarm: true)
            } catch { await engine.finishRequest(keepWarm: false); throw error }
        }
        try await until("Cancelled generation did not reach suspension") { await F5TTSModel.gate.generationEntered }
        cancelled.cancel()
        await F5TTSModel.gate.resumeGeneration()
        do { try await cancelled.value; throw CheckFailure(message: "Cancellation was ignored") }
        catch is CancellationError {}
        try expect(!FileManager.default.fileExists(atPath: destination.path), "Cancelled speech must remove incomplete audio")
        let cancelledLoads = F5TTSModel.loads
        await F5TTSModel.gate.configure(fail: true)
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == cancelledLoads + 1, "Cancelled speech must release the runtime")
        do {
            try await engine.speak(text: "Hello world.", referenceAudio: reference, referenceText: "This is a reference recording.", destination: destination)
            throw CheckFailure(message: "Generation failure was ignored")
        } catch StubFailure.generation { await engine.finishRequest(keepWarm: false) }
        try expect(!FileManager.default.fileExists(atPath: destination.path), "Failed speech must remove incomplete audio")
        await F5TTSModel.gate.configure()
        await engine.unload()
        try Data("corrupt".utf8).write(to: root.appendingPathComponent("model.safetensors"))
        let integrityLoads = F5TTSModel.loads
        do {
            try await engine.load(localBundle: root)
            throw CheckFailure(message: "A cold reload must reject a corrupted bundle")
        } catch is CheckFailure { throw CheckFailure(message: "A cold reload accepted a corrupted bundle") }
          catch { await engine.finishRequest(keepWarm: false) }
        try expect(F5TTSModel.loads == integrityLoads, "Corruption must fail before constructing the runtime")
        print("Warm reuse, expiry, stale timer, in-flight load/generation release, background release, actual generation cancellation/failure cleanup and cold integrity checks passed")
    }
}
