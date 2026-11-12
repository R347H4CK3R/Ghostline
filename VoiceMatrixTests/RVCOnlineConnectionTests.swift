import XCTest
import CryptoKit
@testable import VoiceMatrix

final class RVCOnlineConnectionTests: XCTestCase {
    private func wav() -> Data {
        // Independently constructed 0.2-second, mono PCM16, 40 kHz RIFF fixture.
        var bytes = Data("RIFF".utf8)
        func le(_ value: Int, _ count: Int) { for i in 0..<count { bytes.append(UInt8((value >> (8 * i)) & 255)) } }
        le(16036, 4); bytes.append(Data("WAVEfmt ".utf8)); le(16, 4)
        le(1, 2); le(1, 2); le(40000, 4); le(80000, 4); le(2, 2); le(16, 2)
        bytes.append(Data("data".utf8)); le(16000, 4); bytes.append(Data(repeating: 1, count: 16000))
        return bytes
    }
    private func model() -> RVCOnlineModel {
        RVCOnlineModel(id: "private_speaker", name: "Private speaker", categories: ["Private"],
                       modelSHA256: String(repeating: "a", count: 64), indexSHA256: String(repeating: "b", count: 64),
                       revision: String(repeating: "c", count: 64), identityVerified: false, likenessVerified: false)
    }
    private func sha(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }
    func testRequestHashesActualAudioAndPinsModel() throws {
        let input = wav(), chosen = model()
        let request = try RVCOnlineConnection.request(model: chosen, wav: input,
                                                     id: UUID(uuidString: "d49dd0a6-16f8-48bb-9d13-123456789abc")!)
        XCTAssertEqual(request.inputSHA256, sha(input))
        XCTAssertEqual(request.requestID, "d49dd0a6-16f8-48bb-9d13-123456789abc")
        XCTAssertEqual(Data(base64Encoded: request.wavBase64), input)
        XCTAssertEqual(request.revision, chosen.revision)
        XCTAssertEqual(request.modelSHA256, chosen.modelSHA256)
        XCTAssertEqual(request.indexSHA256, chosen.indexSHA256)
    }
    func testRequestRejectsOversizedAndNonWAVInput() {
        XCTAssertThrowsError(try RVCOnlineConnection.request(model: model(), wav: Data(repeating: 0, count: 3_145_729)))
        XCTAssertThrowsError(try RVCOnlineConnection.request(model: model(), wav: Data("not a WAV".utf8)))
    }
    func testResultRequiresMatchingHeaderDigestBytesAndDuration() throws {
        let audio = wav(), hash = sha(audio)
        let expected = RVCOnlineSnapshot.Result(sha256: hash, bytes: 16044, sampleRate: 40000, seconds: 0.2)
        XCTAssertNoThrow(try RVCOnlineConnection.validateResult(audio, headerSHA256: hash, expected: expected))
        XCTAssertThrowsError(try RVCOnlineConnection.validateResult(audio, headerSHA256: nil, expected: expected))
        XCTAssertThrowsError(try RVCOnlineConnection.validateResult(audio, headerSHA256: String(repeating: "a", count: 64), expected: expected))
        var tampered = audio; tampered[tampered.count - 1] ^= 1
        XCTAssertNotEqual(tampered, audio)
        XCTAssertThrowsError(try RVCOnlineConnection.validateResult(tampered, headerSHA256: hash, expected: expected))
        XCTAssertThrowsError(try RVCOnlineConnection.validateResult(Data(audio.dropLast()), headerSHA256: hash, expected: expected))
        let wrongDuration = RVCOnlineSnapshot.Result(sha256: hash, bytes: 16044, sampleRate: 40000, seconds: 0.2003)
        XCTAssertThrowsError(try RVCOnlineConnection.validateResult(audio, headerSHA256: hash, expected: wrongDuration))
    }
    func testConnectionRejectsUnsafeOriginAndHeaderCredential() throws {
        XCTAssertNoThrow(try RVCOnlineConnection(root: URL(string: "https://laptop.test/")!, token: nil))
        XCTAssertThrowsError(try RVCOnlineConnection(root: URL(string: "http://laptop.test/")!, token: nil))
        XCTAssertThrowsError(try RVCOnlineConnection(root: URL(string: "https://laptop.test/?other=true")!, token: nil))
        XCTAssertThrowsError(try RVCOnlineConnection(root: URL(string: "https://laptop.test/")!, token: String(repeating: "x", count: 32) + "\r\nInjected: true"))
        XCTAssertThrowsError(try RVCOnlineConnection(root: URL(string: "https://laptop.test/")!, token: "short"))
    }
}
