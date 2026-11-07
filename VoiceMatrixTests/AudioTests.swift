import XCTest
import AVFoundation
@testable import VoiceMatrix

final class AudioTests: XCTestCase {
    func testBundledProfilesHaveUniqueIDsAndAssets() throws {
        let (root, manifest) = try Catalog.read()
        XCTAssertEqual(manifest.voices.count, 37)
        XCTAssertEqual(Set(manifest.voices.map(\.id)).count, 37)
        XCTAssertEqual(Set(manifest.voices.map(\.sha256)).count, 37)
        try Catalog.validate(root: root, manifest: manifest)
    }
    func testBundledNeuralVoiceGeneratesDecodableNonSilentWAV() async throws {
        let (root, manifest) = try Catalog.read()
        let voice = try XCTUnwrap(manifest.voices.first { $0.id == "en_us_Zoey" })
        let engine = NeuralSpeech(computeUnits: .cpuOnly)
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("Neural-test-\(UUID()).wav")
        defer { try? FileManager.default.removeItem(at: output) }
        let started = Date()
        print("VoiceMatrix neural smoke: starting local CPU model load and WAV synthesis")
        let duration = try await engine.generate(text: "Hello from VoiceMatrix.", voice: voice, root: root, manifest: manifest, output: output, progress: { print("VoiceMatrix test phase: " + $0) })
        print("VoiceMatrix neural smoke: completed, elapsed=\(Date().timeIntervalSince(started)), audioSeconds=\(duration)")
        XCTAssertGreaterThan(duration, 0.1)
        let decoded = try AVAudioFile(forReading: output)
        XCTAssertEqual(decoded.fileFormat.sampleRate, 24000)
        XCTAssertGreaterThan(decoded.length, 2400)
        await engine.unload()
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
