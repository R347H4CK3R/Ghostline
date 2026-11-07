import XCTest
import AVFoundation
import CryptoKit
@testable import VoiceMatrix

final class AudioTests: XCTestCase {
    private func inferenceFingerprint(root: URL) throws -> String {
        let data = try Data(contentsOf: root.appendingPathComponent("inference-fingerprint.json"))
        let metadata = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let value = try XCTUnwrap(metadata["sha256"] as? String)
        XCTAssertEqual(value.count, 64)
        return value
    }
    func testBundledProfilesHaveUniqueIDsAndAssets() throws {
        let (root, manifest) = try Catalog.read()
        XCTAssertEqual(manifest.voices.count, 538)
        XCTAssertEqual(Set(manifest.voices.map(\.id)).count, 538)
        XCTAssertEqual(Set(manifest.voices.map(\.sha256)).count, 538)
        try Catalog.validate(root: root, manifest: manifest)
    }
    func testAllBundledNeuralVoicesGenerateDecodableNonSilentWAV() async throws {
        executionTimeAllowance = 1500
        let (root, manifest) = try Catalog.read()
        let engine = NeuralSpeech(computeUnits: .cpuOnly)
        let memory = SampledMemoryPeak()
        let monitoring = Task {
            while !Task.isCancelled { await memory.sample(); try? await Task.sleep(nanoseconds: 50_000_000) }
        }
        defer { monitoring.cancel() }

        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("VoiceMatrix-QA")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        var results: [[String: Any]] = []
        var englishChecks: [[String: Any]] = []
        struct Shard: Decodable { let index, count: Int }
        let shard: Shard
        if let url = Bundle(for: AudioTests.self).url(forResource: "qa-shard", withExtension: "json") { shard = try JSONDecoder().decode(Shard.self, from: Data(contentsOf: url)) }
        else { shard = Shard(index: 0, count: 1) }
        let selected = manifest.voices.enumerated().filter { $0.offset % shard.count == shard.index }.map(\.element)
        for voice in selected {
            let output = folder.appendingPathComponent(voice.id).appendingPathExtension("wav")
            let started = Date()
            print("VoiceMatrix QA starting profile=\(voice.id)")
            let duration = try await engine.generate(text: "Hello. This is a voice test.", voice: voice, root: root, manifest: manifest, output: output)
            let decoded = try AVAudioFile(forReading: output)
            XCTAssertGreaterThan(duration, 0.1, voice.id)
            XCTAssertEqual(decoded.fileFormat.sampleRate, voice.engine == "phonon31m" ? 24000 : 22050, voice.id)
            XCTAssertGreaterThan(decoded.length, 2400, voice.id)
            let digest = SHA256.hash(data: try Data(contentsOf: output)).map { String(format: "%02x", $0) }.joined()
            let clipAttachment = XCTAttachment(contentsOfFile: output)
            clipAttachment.name = voice.id + ".wav"; clipAttachment.lifetime = .keepAlways; add(clipAttachment)
            results.append(["id": voice.id, "audioSeconds": duration, "elapsedSeconds": Date().timeIntervalSince(started), "audioSHA256": digest, "embeddingSHA256": voice.sha256, "nonSilentWAVDecoded": true])
            print("VoiceMatrix QA passed profile=\(voice.id) audioSeconds=\(duration)")
            if voice.category == "International Voices" || voice.engine == "phonon31m-openvoicev2" {
                let text = "Please bring three blue notebooks to the quiet room before lunch."
                let varied = folder.appendingPathComponent(voice.id + "-english").appendingPathExtension("wav")
                let variedDuration = try await engine.generate(text: text, voice: voice, root: root, manifest: manifest, output: varied)
                XCTAssertGreaterThan(variedDuration, 0.1, voice.id)
                let variedFile = try AVAudioFile(forReading: varied)
                XCTAssertGreaterThan(variedFile.length, 2400, voice.id)
                let variedHash = SHA256.hash(data: try Data(contentsOf: varied)).map { String(format: "%02x", $0) }.joined()
                englishChecks.append(["id": voice.id, "file": varied.lastPathComponent, "referenceText": text, "audioSHA256": variedHash, "audioSeconds": variedDuration])
                let attachment = XCTAttachment(contentsOfFile: varied)
                attachment.name = varied.lastPathComponent; attachment.lifetime = .keepAlways; add(attachment)
            }
        }
        XCTAssertEqual(results.count, selected.count)
        let report: [String: Any] = ["schemaVersion": 1, "kind": "text-to-speech", "platform": "iOS Simulator", "engine": "phonon31m", "modelRevision": manifest.revision, "inferenceFingerprint": try inferenceFingerprint(root: root), "physicalDeviceVerified": 0, "listeningVerified": 0, "profiles": results, "additionalEnglishChecks": englishChecks, "shardIndex": shard.index, "shardCount": shard.count, "sampledPeakPhysicalFootprintBytes": await memory.bytes(), "memoryMeasurement": "50ms samples of simulator test-host process physical footprint; not iPhone peak memory"]
        let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: folder.appendingPathComponent("voice-synthesis-results.json"), options: .atomic)
        let reportAttachment = XCTAttachment(contentsOfFile: folder.appendingPathComponent("voice-synthesis-results.json"))
        reportAttachment.name = "voice-synthesis-results.json"; reportAttachment.lifetime = .keepAlways; add(reportAttachment)
        await engine.unload()
    }
    func testEveryIncludedVoiceChangesAControlledRecording() async throws {
        executionTimeAllowance = 1500
        struct Shard: Decodable { let index, count: Int }
        let (root, manifest) = try Catalog.read()
        let shard: Shard
        if let url = Bundle(for: AudioTests.self).url(forResource: "qa-shard", withExtension: "json") { shard = try JSONDecoder().decode(Shard.self, from: Data(contentsOf: url)) }
        else { shard = Shard(index: 0, count: 1) }
        let selected = manifest.voices.enumerated().filter { $0.offset % shard.count == shard.index }.map(\.element)
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("VoiceMatrix-QA")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let source = folder.appendingPathComponent("controlled-recording.wav")
        let text = "Please bring three blue notebooks to the quiet room before lunch."
        let base = try XCTUnwrap(manifest.voices.first { $0.id == "en_us_Micah" })
        let engine = NeuralSpeech(computeUnits: .cpuOnly)
        _ = try await engine.generate(text: text, voice: base, root: root, manifest: manifest, output: source)
        var checks: [[String: Any]] = []
        for voice in selected {
            let output = folder.appendingPathComponent("vc-" + voice.id).appendingPathExtension("wav")
            let started = Date()
            let duration = try await engine.convertRecording(source: source, voice: voice, root: root, manifest: manifest, output: output, progress: { _ in })
            let decoded = try AVAudioFile(forReading: output)
            XCTAssertEqual(decoded.fileFormat.sampleRate, 22050)
            XCTAssertGreaterThan(decoded.length, 2400)
            let hash = SHA256.hash(data: try Data(contentsOf: output)).map { String(format: "%02x", $0) }.joined()
            checks.append(["id": voice.id, "file": output.lastPathComponent, "referenceText": text, "embeddingSHA256": voice.sha256, "audioSHA256": hash, "audioSeconds": duration, "elapsedSeconds": Date().timeIntervalSince(started), "nonSilentWAVDecoded": true])
            let attachment = XCTAttachment(contentsOfFile: output)
            attachment.name = output.lastPathComponent; attachment.lifetime = .keepAlways; add(attachment)
        }
        await engine.unload()
        XCTAssertEqual(checks.count, selected.count)
        let report: [String: Any] = ["kind": "voice-conversion", "modelRevision": manifest.revision, "inferenceFingerprint": try inferenceFingerprint(root: root), "profiles": checks]
        let url = folder.appendingPathComponent("voice-conversion-results.json")
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: url)
        let attachment = XCTAttachment(contentsOfFile: url)
        attachment.name = url.lastPathComponent; attachment.lifetime = .keepAlways; add(attachment)
    }
    func testTemporaryAudioCleanupOnlyRemovesOwnedTemporaryFiles() throws {
        let root = FileManager.default.temporaryDirectory
        let owned = root.appendingPathComponent("Speech-cleanup-\(UUID()).wav")
        let unrelated = root.appendingPathComponent("Unrelated-\(UUID()).wav")
        try Data([1]).write(to: owned); try Data([2]).write(to: unrelated)
        defer { try? FileManager.default.removeItem(at: unrelated) }
        TemporaryAudio.discard(owned); TemporaryAudio.discard(unrelated)
        XCTAssertFalse(FileManager.default.fileExists(atPath: owned.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: unrelated.path))
    }
    func testTraversalRejected() throws {
        let root = FileManager.default.temporaryDirectory
        let manifest = VoiceManifest(schemaVersion: 1, engine: "phonon31m", revision: "test", files: [.init(path: "../invalid", sha256: "0", size: 1)], voices: [])
        XCTAssertThrowsError(try Catalog.validate(root: root, manifest: manifest))
    }
    @MainActor func testSaveRemainsDeduplicatedAfterRename() throws {
        let source = FileManager.default.temporaryDirectory.appendingPathComponent("test-\(UUID()).wav")
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1))
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 2400))
        buffer.frameLength = 2400
        for i in 0..<2400 { buffer.floatChannelData![0][i] = Float(sin(Double(i) * 0.1)) * 0.2 }
        var writer: AVAudioFile? = try AVAudioFile(forWriting: source, settings: format.settings)
        try writer?.write(from: buffer); writer = nil
        defer { try? FileManager.default.removeItem(at: source) }
        let store = AudioStore()
        store.save(source)
        let saved = try XCTUnwrap(store.recordings.first { $0.id == source.lastPathComponent })
        let renamed = "Renamed-\(UUID())"
        store.rename(saved, to: renamed)
        store.save(source)
        XCTAssertTrue(store.isSaved(source))
        XCTAssertFalse(store.recordings.contains { $0.id == source.lastPathComponent })
        let result = try XCTUnwrap(store.recordings.first { $0.name == renamed })
        XCTAssertGreaterThan(try AVAudioFile(forReading: result.url).length, 0)
        store.delete(result)
    }
}
