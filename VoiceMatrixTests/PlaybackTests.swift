import XCTest
import AVFoundation
import CryptoKit
@testable import VoiceMatrix

@MainActor final class PlaybackTests: XCTestCase {
    private func fixture() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("Playback-test-\(UUID()).wav")
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1))
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 120000))
        buffer.frameLength = 120000
        let samples = try XCTUnwrap(buffer.floatChannelData?[0])
        for i in 0..<120000 { samples[i] = Float(sin(Double(i) * 2 * .pi * 440 / 24000)) * 0.2 }
        var writer: AVAudioFile? = try AVAudioFile(forWriting: url, settings: [
            AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 24000.0,
            AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false
        ])
        try writer?.write(from: buffer); writer = nil
        return url
    }
    func testValidPCMStartsAndStopClearsPlayback() throws {
        let url = try fixture()
        defer { try? FileManager.default.removeItem(at: url) }
        let store = AudioStore()
        defer { store.stop() }
        store.play(url)
        XCTAssertNil(store.error)
        XCTAssertEqual(store.playing, url)
        store.stop()
        XCTAssertNil(store.playing)
    }
    func testMissingFileReportsFailureAndCanRecover() throws {
        let url = try fixture()
        defer { try? FileManager.default.removeItem(at: url) }
        let store = AudioStore()
        defer { store.stop() }
        store.play(url.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".wav"))
        XCTAssertNil(store.playing)
        XCTAssertNotNil(store.error)
        store.play(url)
        XCTAssertNil(store.error)
        XCTAssertEqual(store.playing, url)
    }
    func testSupersededPlayerCallbacksCannotClearCurrentPlayback() async throws {
        let url = try fixture()
        defer { try? FileManager.default.removeItem(at: url) }
        let store = AudioStore()
        defer { store.stop() }
        let oldPlayer = try AVAudioPlayer(contentsOf: url)
        store.play(url)
        XCTAssertEqual(store.playing, url)
        store.audioPlayerDidFinishPlaying(oldPlayer, successfully: false)
        store.audioPlayerDecodeErrorDidOccur(oldPlayer, error: nil)
        // Delegate methods enqueue MainActor work.
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(store.playing, url)
        XCTAssertNil(store.error)
    }
    func testImportedReferenceAdvancesAndReplays() async throws {
        let source = try fixture()
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("Playback-import-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: source); try? FileManager.default.removeItem(at: root) }
        let collection = root.appendingPathComponent("collection")
        let voiceFolder = collection.appendingPathComponent("test-voice")
        try FileManager.default.createDirectory(at: voiceFolder, withIntermediateDirectories: true)
        let bytes = try Data(contentsOf: source)
        try bytes.write(to: voiceFolder.appendingPathComponent("reference.wav"))
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let reference = CharacterReference(id: "test-voice", name: "Synthetic playback fixture",
            source: "Generated test tone", permission: "Original test fixture", referenceText: "Test only.",
            schemaVersion: 1, kind: "f5-reference", engine: "F5TTS_v1_Base",
            referenceFile: "reference.wav", referenceSHA256: hash, trainedModel: false,
            categories: ["Test"], referenceBytes: bytes.count, seconds: 5)
        try JSONEncoder().encode(reference).write(to: voiceFolder.appendingPathComponent("manifest.json"))
        try Data(#"{"schemaVersion":1,"voices":[{"id":"test-voice","folder":"test-voice"}]}"#.utf8)
            .write(to: collection.appendingPathComponent("collection.json"))
        let library = CharacterFolderStore(root: root.appendingPathComponent("private"))
        _ = try await library.importCollection(at: collection)
        let imported = try await library.referenceURL(id: "test-voice")
        let store = AudioStore()
        defer { store.stop() }
        for _ in 0..<2 {
            store.play(imported)
            XCTAssertNil(store.error)
            XCTAssertEqual(store.playing, imported)
            XCTAssertEqual(store.durationSeconds, 5, accuracy: 0.1)
            try await Task.sleep(nanoseconds: 400_000_000)
            XCTAssertGreaterThan(store.elapsedSeconds, 0.1, "Native playback must advance, not merely accept play().")
            store.stop()
            XCTAssertNil(store.playing)
        }
        XCTAssertEqual(try Data(contentsOf: imported), bytes, "Listening must preserve the private reference.")
    }
    func testMicrophoneOwnershipBlocksPlaybackWithFeedback() throws {
        let url = try fixture()
        defer { try? FileManager.default.removeItem(at: url) }
        let store = AudioStore()
        let lease = try XCTUnwrap(store.claimMicrophone())
        defer { store.releaseMicrophone(lease); store.stop() }
        store.play(url)
        XCTAssertNil(store.playing)
        XCTAssertEqual(store.error, "Stop recording before listening to audio.")
    }
}
