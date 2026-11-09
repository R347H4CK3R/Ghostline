import Foundation
import CryptoKit
import F5TTS

func trace(_ values: Any...) { FileHandle.standardError.write(Data((values.map { String(describing: $0) }.joined(separator: " ") + "\n").utf8)) }
struct CheckFailure: Error { let message: String }
func expect(_ value: Bool, _ message: String) throws { if !value { throw CheckFailure(message: message) } }

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
        let engine = F5ReferenceEngine(idleRetention: .milliseconds(80))
        try await engine.load(localBundle: root)
        await engine.finishRequest(keepWarm: true)
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == 1, "A second request must reuse the validated loaded engine")
        await engine.finishRequest(keepWarm: true)
        let expiryStart = ProcessInfo.processInfo.systemUptime
        trace("expiry start", expiryStart, F5TTSModel.loads, F5TTSModel.unloads)
        try await Task.sleep(for: .milliseconds(130))
        trace("expiry after sleep", ProcessInfo.processInfo.systemUptime-expiryStart, F5TTSModel.loads, F5TTSModel.unloads)
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == 2, "Idle expiry must release the engine")
        await engine.finishRequest(keepWarm: true)
        let timerStart = ProcessInfo.processInfo.systemUptime
        trace("stale start", timerStart, "loads", F5TTSModel.loads, "unloads", F5TTSModel.unloads)
        try await Task.sleep(for: .milliseconds(20))
        trace("before begin", ProcessInfo.processInfo.systemUptime-timerStart, "loads", F5TTSModel.loads, "unloads", F5TTSModel.unloads)
        try await engine.load(localBundle: root)
        trace("after begin", ProcessInfo.processInfo.systemUptime-timerStart, "loads", F5TTSModel.loads, "unloads", F5TTSModel.unloads)
        try await Task.sleep(for: .milliseconds(100))
        trace("after deadline", ProcessInfo.processInfo.systemUptime-timerStart, "loads", F5TTSModel.loads, "unloads", F5TTSModel.unloads)
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
        let task = Task {
            try await engine.load(localBundle: root)
            try? await Task.sleep(for: .seconds(10))
            await engine.finishRequest(keepWarm: true)
        }
        try await Task.sleep(for: .milliseconds(20))
        task.cancel()
        try await task.value
        let cancelledLoads = F5TTSModel.loads
        try await engine.load(localBundle: root)
        try expect(F5TTSModel.loads == cancelledLoads + 1, "Cancellation must not retain an engine")
        await engine.unload()
        try Data("corrupt".utf8).write(to: root.appendingPathComponent("model.safetensors"))
        let integrityLoads = F5TTSModel.loads
        do {
            try await engine.load(localBundle: root)
            throw CheckFailure(message: "A cold reload must reject a corrupted bundle")
        } catch is CheckFailure { throw CheckFailure(message: "A cold reload accepted a corrupted bundle") }
          catch { await engine.finishRequest(keepWarm: false) }
        try expect(F5TTSModel.loads == integrityLoads, "Corruption must fail before constructing the runtime")
        print("Warm reuse, expiry, stale timer, pressure, background release, cancellation and cold integrity checks passed")
    }
}
