import XCTest
import CryptoKit
@testable import VoiceMatrix

final class RVCOnlineFileTests: XCTestCase {
    private func wav() -> Data {
        var data = Data("RIFF".utf8)
        func le(_ value: Int, _ count: Int) { for i in 0..<count { data.append(UInt8((value >> (8 * i)) & 255)) } }
        le(16036, 4); data.append(Data("WAVEfmt ".utf8)); le(16, 4)
        le(1, 2); le(1, 2); le(40000, 4); le(80000, 4); le(2, 2); le(16, 2)
        data.append(Data("data".utf8)); le(16000, 4); data.append(Data(repeating: 1, count: 16000))
        return data
    }
    func testImportRetainsExactBytesWithoutResampling() throws {
        let source = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at: source) }
        let original = wav(); try original.write(to: source)
        let imported = try RVCOnlineFiles.read(source)
        XCTAssertEqual(imported.data, original)
        XCTAssertEqual(imported.sampleRate, 40000)
        XCTAssertEqual(imported.seconds, 0.2)
    }
    func testOversizedAndLinkedInputsAreRejected() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let source = folder.appendingPathComponent("large.wav")
        try Data(repeating: 0, count: 3_145_729).write(to: source)
        XCTAssertThrowsError(try RVCOnlineFiles.read(source))
        try wav().write(to: source)
        let link = folder.appendingPathComponent("link.wav")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: source)
        XCTAssertThrowsError(try RVCOnlineFiles.read(link))
    }
    func testTemporaryOutputIsVerifiedAndUsesExistingAudioOwnershipConvention() throws {
        let data = wav()
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        let result = RVCOnlineSnapshot.Result(sha256: digest, bytes: data.count, sampleRate: 40000, seconds: 0.2)
        let url = try RVCOnlineFiles.verifiedTemporary(data, result: result)
        defer { TemporaryAudio.discard(url) }
        XCTAssertTrue(url.lastPathComponent.hasPrefix("Converted-RVC-"))
        XCTAssertEqual(try Data(contentsOf: url), data)
        var corrupted = data; corrupted[corrupted.count - 1] ^= 1
        XCTAssertThrowsError(try RVCOnlineFiles.verifiedTemporary(corrupted, result: result))
    }
}
