import XCTest
@testable import VoiceMatrix

@MainActor final class BundledASRTests: XCTestCase {
    func testMissingBundledAssetsFailWithoutSpeechAuthorization() async throws {
        let transcriber = OnDeviceTranscription(bundle: nil)
        do { try await transcriber.authorize(); XCTFail("Missing models cannot pass") }
        catch { XCTAssertTrue(error is BundledASRAssets.Failure) }
        XCTAssertNil(transcriber.lastEvidence)
    }
    func testNonlocalAudioIsRejectedBeforeModelLoading() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        let transcriber = OnDeviceTranscription(bundle: root)
        do { _ = try await transcriber.transcribe(URL(string: "https://example.invalid/audio.wav")!); XCTFail("No remote inputs") }
        catch OnDeviceTranscription.Failure.invalidAudio { }
        XCTAssertNil(transcriber.lastEvidence)
    }
    func testOversizedFileIsRejectedBeforeModelLoading() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("oversize.wav")
        XCTAssertTrue(FileManager.default.createFile(atPath: source.path, contents: nil))
        let handle = try FileHandle(forWritingTo: source)
        try handle.truncate(atOffset: 8_388_609); try handle.close()
        let transcriber = OnDeviceTranscription(bundle: root)
        do { _ = try await transcriber.transcribe(source); XCTFail("Oversized input cannot pass") }
        catch OnDeviceTranscription.Failure.invalidAudio { }
        XCTAssertNil(transcriber.lastEvidence)
        XCTAssertEqual(try source.resourceValues(forKeys: [.fileSizeKey]).fileSize, 8_388_609)
    }
    func testMissingActualTokenEvidenceCannotUseSDKFallback() {
        XCTAssertNil(BundledASRPolicy.admittedTokenMean([]))
        XCTAssertNil(BundledASRPolicy.admittedTokenMean([.nan]))
        XCTAssertNil(BundledASRPolicy.admittedTokenMean([.infinity]))
        XCTAssertNil(BundledASRPolicy.admittedTokenMean([0.34]))
        XCTAssertEqual(BundledASRPolicy.admittedTokenMean([0.35]), 0.35)
        XCTAssertEqual(BundledASRPolicy.admittedTokenMean([0.4, 0.8])!, 0.6, accuracy: 0.0001)
    }
    func testInputDigestRejectsSameSizeReplacementAndTruncation() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("input.wav")
        try Data([1,2,3,4]).write(to: source)
        let first = try OnDeviceTranscription.inputDigest(source, byteCount: 4)
        XCTAssertEqual(try OnDeviceTranscription.inputDigest(source, byteCount: 4, matching: first), first)
        try Data([1,2,3,5]).write(to: source, options: .atomic)
        XCTAssertThrowsError(try OnDeviceTranscription.inputDigest(source, byteCount: 4, matching: first))
        try Data([1,2]).write(to: source, options: .atomic)
        XCTAssertThrowsError(try OnDeviceTranscription.inputDigest(source, byteCount: 4, matching: first))
    }

}
