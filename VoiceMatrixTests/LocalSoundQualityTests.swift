import Foundation
import XCTest
import CryptoKit
import SoundAnalysis
@testable import VoiceMatrix

final class LocalSoundQualityTests: XCTestCase {
    func testBuiltInClassifierExposesRequiredIdentifiers() throws {
        let request=try SNClassifySoundRequest(classifierIdentifier: .version1)
        XCTAssertTrue(Set(["speech","music","singing"]).isSubset(of:Set(request.knownClassifications)))
    }
    private func fixture() throws -> URL {
        let url=try XCTUnwrap(Bundle(for:LocalSoundQualityTests.self).url(forResource:"conversion-reference",withExtension:"wav"))
        let data=try Data(contentsOf:url)
        guard data.count==123392,SHA256.hash(data:data).map({String(format:"%02x",$0)}).joined()=="0840a3b08d2d438804e760afa54bc1c9cdf1c8b33bffdc1ab458be4ab3740cd2" else {
            throw NSError(domain:"Changed synthetic fixture",code:1)
        }
        return url
    }
    func testPinnedNeutralSpeechPassesScreeningWithoutBeingCalledSeparated() async throws {
        let url=try fixture(), before=try Data(contentsOf:url)
        let evidence=try await LocalSoundQuality.analyze(source:url) { _ in }
        XCTAssertFalse(evidence.frames.isEmpty)
        XCTAssertTrue(evidence.decision.admitted,evidence.decision.reason)
        XCTAssertTrue(evidence.decision.reason.contains("not proof"))
        XCTAssertEqual(try Data(contentsOf:url),before)
        let attachment=XCTAttachment(data:try JSONEncoder().encode(evidence),uniformTypeIdentifier:"public.json")
        attachment.name="Built-in classifier scores on pinned neutral synthetic speech"
        attachment.lifetime = .keepAlways;add(attachment)
    }
    func testSilenceAndSyntheticToneAreNotAdmittedAsCleanSpeech() async throws {
        for tone in [false,true] {
            let url=try makeWave(tone:tone)
            defer { try? FileManager.default.removeItem(at:url) }
            let before=try Data(contentsOf:url)
            let evidence=try await LocalSoundQuality.analyze(source:url) { _ in }
            XCTAssertFalse(evidence.decision.admitted,"Non-speech synthetic input was admitted")
            XCTAssertEqual(try Data(contentsOf:url),before)
        }
    }
    func testCancellationDoesNotProduceAnAdmission() async throws {
        let url=try fixture()
        let task=Task { try await LocalSoundQuality.analyze(source:url) { _ in } }
        task.cancel()
        do { _=try await task.value;XCTFail("Canceled screening returned a result") }
        catch is CancellationError { }
    }
    func testRemoteInputIsRejectedWithoutARequest() async {
        do { _=try await LocalSoundQuality.analyze(source:URL(string:"https://example.invalid/audio.wav")!) { _ in };XCTFail("Remote source accepted") }
        catch LocalSoundQuality.Failure.invalidSource { }
        catch { XCTFail("Unexpected error: \(error)") }
    }
    private func makeWave(tone:Bool) throws -> URL {
        var data=Data()
        func tag(_ value:String) { data.append(contentsOf:value.utf8) }
        func u16(_ value:UInt16) { var v=value.littleEndian;withUnsafeBytes(of:&v) { data.append(contentsOf:$0) } }
        func u32(_ value:UInt32) { var v=value.littleEndian;withUnsafeBytes(of:&v) { data.append(contentsOf:$0) } }
        let frames=24_000*3
        tag("RIFF");u32(UInt32(frames*2+36));tag("WAVE");tag("fmt ");u32(16);u16(1);u16(1);u32(24_000);u32(48_000);u16(2);u16(16);tag("data");u32(UInt32(frames*2))
        for i in 0..<frames { let sample=tone ? Int16(sin(Double(i)*2*Double.pi*440/24_000)*8192) : 0;u16(UInt16(bitPattern:sample)) }
        let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".wav")
        try data.write(to:url);return url
    }
}
