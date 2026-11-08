import XCTest
import AVFoundation
import CryptoKit
@testable import CharacterRuntimeHost

final class CharacterOfflineConversionTests: XCTestCase {
    func testImportedReferenceProducesDecodableChangedRecording() async throws {
        let testBundle = Bundle(for: Self.self)
        let source = try XCTUnwrap(testBundle.url(forResource: "conversion-source", withExtension: "wav"))
        let reference = try XCTUnwrap(testBundle.url(forResource: "conversion-reference", withExtension: "wav"))
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("CharacterConversionQA")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let destination = root.appendingPathComponent("reference-conditioned-conversion.wav")
        let converter = CharacterVoiceConversion()
        let result = try await converter.run(reference: reference, source: source, destination: destination) { print("Character conversion stage: " + $0) }
        XCTAssertLessThan(abs(result.sourceSeconds - result.outputSeconds), 0.04)
        let samples = try ConversionAudio.readMono(destination, minimumSeconds: 0.15)
        XCTAssertGreaterThan(samples.count, 2205)
        XCTAssertTrue(samples.allSatisfy { $0.isFinite && abs($0) < 1 })
        XCTAssertGreaterThan(samples.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(samples.count), 1e-8)
        let hash: (URL) throws -> String = { SHA256.hash(data: try Data(contentsOf: $0)).map { String(format: "%02x", $0) }.joined() }
        let report: [String: Any] = ["sharedModelManifestSHA256":try hash(Bundle.main.url(forResource: "OpenVoice", withExtension: nil)!.appendingPathComponent("model-manifest.json")), "sourceAudioSHA256":try hash(source), "referenceAudioSHA256":try hash(reference), "outputSHA256":try hash(destination), "sourceSeconds":result.sourceSeconds, "outputSeconds":result.outputSeconds, "expectedText":"I found a strange device near the portal.", "decodedNonSilentWAV":true, "physicalDeviceVerified":false, "likenessVerified":false, "scope":"iOS simulator diagnostic reference conversion using actual CoreML models"]
        try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys,.prettyPrinted]).write(to: root.appendingPathComponent("conversion-result.json"), options: .atomic)
    }
}
