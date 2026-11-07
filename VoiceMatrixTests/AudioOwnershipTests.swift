import XCTest
import AVFoundation
@testable import VoiceMatrix
@MainActor final class AudioOwnershipTests: XCTestCase {
    func testRetainedAudioCannotSwitchSessionDuringMicrophoneCapture() throws {
        let session = AVAudioSession.sharedInstance()
        let original = session.category
        defer { try? session.setCategory(original) }
        try session.setCategory(.playAndRecord, mode: .default)
        let audio = AudioStore()
        let lease = try XCTUnwrap(audio.claimMicrophone())
        audio.play(FileManager.default.temporaryDirectory.appendingPathComponent("unavailable-previous-conversion.wav"))
        XCTAssertTrue(audio.microphoneInUse)
        XCTAssertNil(audio.playing)
        XCTAssertEqual(session.category, .playAndRecord)
        XCTAssertNotNil(audio.error)
        audio.releaseMicrophone(lease)
        XCTAssertFalse(audio.microphoneInUse)
    }
    func testOldPermissionCallbackCannotReleaseAnotherRecordingSession() throws {
        let audio = AudioStore()
        let first = try XCTUnwrap(audio.claimMicrophone())
        XCTAssertNil(audio.claimMicrophone())
        audio.releaseMicrophone(first)
        let second = try XCTUnwrap(audio.claimMicrophone())
        audio.releaseMicrophone(first)
        XCTAssertTrue(audio.microphoneInUse)
        audio.releaseMicrophone(second)
        XCTAssertFalse(audio.microphoneInUse)
    }
}
