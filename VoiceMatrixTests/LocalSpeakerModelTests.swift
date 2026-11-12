import Foundation
import AVFoundation
import CryptoKit
import XCTest
@testable import VoiceMatrix

final class LocalSpeakerModelTests: XCTestCase {
    /// Runs real bundled CoreML inference. Silence must not produce invented speakers.
    /// This is not a two-speaker accuracy or character-likeness test.
    func testBundledModelsRejectSilenceWithoutChangingSource() async throws {
        let source = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        var data = Data()
        func tag(_ value:String) { data.append(contentsOf:value.utf8) }
        func u16(_ value:UInt16) { var v=value.littleEndian;withUnsafeBytes(of:&v) { data.append(contentsOf:$0) } }
        func u32(_ value:UInt32) { var v=value.littleEndian;withUnsafeBytes(of:&v) { data.append(contentsOf:$0) } }
        let count=16_000*10*2
        tag("RIFF");u32(UInt32(count+36));tag("WAVE");tag("fmt ");u32(16);u16(1);u16(1);u32(16_000);u32(32_000);u16(2);u16(16);tag("data");u32(UInt32(count));data.append(Data(count:count))
        try data.write(to:source)
        defer { try? FileManager.default.removeItem(at:source) }
        do {
            let result=try await LocalSpeakerDiarization.analyze(source:source) { _ in }
            XCTAssertTrue(result.segments.isEmpty,"Silence was attributed to a speaker")
            XCTAssertTrue(result.speakerWindows.isEmpty)
        } catch {
            XCTAssertEqual(error.localizedDescription,"No speech detected in audio","Real bundled-model execution failed before a valid silence result")
        }
        XCTAssertEqual(try Data(contentsOf:source),data)
    }
    /// Positive, real segmentation/embedding/clustering inference on already-public
    /// neutral synthetic speech. This does not measure multi-speaker accuracy.
    func testBundledModelsDetectNeutralSyntheticSpeech() async throws {
        let fixture = try XCTUnwrap(Bundle(for: LocalSpeakerModelTests.self).url(forResource: "conversion-reference", withExtension: "wav"))
        let original = try Data(contentsOf: fixture)
        guard original.count == 123392,
              SHA256.hash(data: original).map({ String(format: "%02x", $0) }).joined() == "0840a3b08d2d438804e760afa54bc1c9cdf1c8b33bffdc1ab458be4ab3740cd2" else {
            XCTFail("Pinned synthetic speech fixture changed; refusing inference"); return
        }
        let input = try AVAudioFile(forReading: fixture)
        XCTAssertEqual(input.fileFormat.sampleRate, 24_000)
        XCTAssertEqual(input.fileFormat.channelCount, 1)
        guard input.length > 0, input.length <= 240_000 else { XCTFail("Fixture duration out of bounds"); return }
        let frames = AVAudioFrameCount(input.length)
        let once = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: input.processingFormat, frameCapacity: frames))
        try input.read(into: once)
        XCTAssertEqual(once.frameLength, frames)
        let repeated = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: input.processingFormat, frameCapacity: frames * 6))
        let from = try XCTUnwrap(once.floatChannelData)[0]
        let to = try XCTUnwrap(repeated.floatChannelData)[0]
        for index in 0..<6 { to.advanced(by: index * Int(frames)).update(from: from, count: Int(frames)) }
        repeated.frameLength = frames * 6
        let source = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at: source) }
        do {
            let output = try AVAudioFile(forWriting: source, settings: input.fileFormat.settings)
            try output.write(from: repeated)
        }
        let before = try Data(contentsOf: source)
        let result = try await LocalSpeakerDiarization.analyze(source: source) { _ in }
        XCTAssertFalse(result.segments.isEmpty, "Neutral synthetic speech produced no model speaker segments")
        XCTAssertFalse(result.speakerWindows.isEmpty, "Positive model inference produced no speaker groups")
        try LocalSpeakerDiarization.validate(result)
        XCTAssertEqual(try Data(contentsOf: source), before)
        XCTAssertEqual(try Data(contentsOf: fixture), original)
    }

}
