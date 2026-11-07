import XCTest
import Foundation
import CryptoKit
@testable import VoiceMatrix
final class ExistingProfileTests: XCTestCase {
    func testEnrollExistingApprovedSpeechVoicesForOfflineConversion() async throws {
        let (_, manifest) = try Catalog.read()
        let references = try XCTUnwrap(Bundle.main.url(forResource: "PhononReferences", withExtension: nil))
        let proof = try JSONSerialization.jsonObject(with: Data(contentsOf: references.appendingPathComponent("voice-synthesis-results.json"))) as! [String: Any]
        XCTAssertEqual(proof["modelRevision"] as? String, manifest.revision)
        let entries = proof["profiles"] as! [[String: Any]]
        let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("VoiceMatrix-Original-Profiles")
        try FileManager.default.createDirectory(at: output.appendingPathComponent("Profiles"), withIntermediateDirectories: true)
        let encoder = OfflineVoiceConverter(computeUnits: .cpuOnly)
        let revision = try await encoder.sourceRevision()
        var results: [[String: Any]] = []
        for voice in manifest.voices {
            let entry = try XCTUnwrap(entries.first { $0["id"] as? String == voice.id })
            XCTAssertEqual(entry["embeddingSHA256"] as? String, voice.sha256)
            let url = references.appendingPathComponent(voice.id).appendingPathExtension("wav")
            let hash = SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
            XCTAssertEqual(entry["audioSHA256"] as? String, hash)
            let vector = try await encoder.extractEmbedding(from: url)
            let profile = ConversionProfile(id: voice.id, ttsEmbeddingSHA256: voice.sha256, converterRevision: revision, referenceAudioSHA256: hash, embedding: vector)
            try JSONEncoder().encode(profile).write(to: output.appendingPathComponent("Profiles").appendingPathComponent(voice.id).appendingPathExtension("json"))
            results.append(["id": voice.id, "referenceSHA256": hash, "ttsEmbeddingSHA256": voice.sha256, "embedding": vector])
        }
        await encoder.unload()
        XCTAssertEqual(results.count, 101)
        let report: [String: Any] = ["converterRevision": revision, "profiles": results, "physicalDeviceVerified": 0, "listeningVerified": 0]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("original-conversion-results.json"))
    }
}
