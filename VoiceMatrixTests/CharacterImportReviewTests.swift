import XCTest
import CryptoKit
@testable import VoiceMatrix

final class CharacterImportReviewTests: XCTestCase {
    func testImportOfflineCopyCorruptRefreshAndReviewInvalidation() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: root) }
        let collection = root.appendingPathComponent("Voices")
        let voice = collection.appendingPathComponent("synthetic-test")
        try fm.createDirectory(at: voice, withIntermediateDirectories: true)
        var wav = Data()
        func tag(_ s: String) { wav.append(contentsOf: s.utf8) }
        func number(_ n: UInt32, _ count: Int) { for i in 0..<count { wav.append(UInt8((n >> (8*i)) & 255)) } }
        tag("RIFF"); number(48036,4); tag("WAVEfmt "); number(16,4); number(1,2); number(1,2)
        number(24000,4); number(48000,4); number(2,2); number(16,2); tag("data"); number(48000,4)
        for i in 0..<24000 { number(i % 2 == 0 ? 4096 : 61440,2) }
        let hash = SHA256.hash(data: wav).map { String(format: "%02x", $0) }.joined()
        let manifest: [String: Any] = ["id":"synthetic-test","name":"Synthetic Test","source":"Generated test fixture","permission":"Original synthetic fixture","referenceText":"A synthetic import test.","schemaVersion":1,"kind":"f5-reference","engine":"F5TTS_v1_Base","referenceFile":"reference.wav","referenceSHA256":hash,"trainedModel":false,"categories":["Test"],"referenceBytes":wav.count,"seconds":1.0]
        try JSONSerialization.data(withJSONObject: manifest).write(to: voice.appendingPathComponent("manifest.json"))
        try wav.write(to: voice.appendingPathComponent("reference.wav"))
        try JSONSerialization.data(withJSONObject:["schemaVersion":1,"voices":[["id":"synthetic-test","folder":"synthetic-test"]]]).write(to: collection.appendingPathComponent("collection.json"))
        let store = CharacterFolderStore(root: root.appendingPathComponent("private"))
        let imported = try await store.importCollection(at: collection)
        XCTAssertEqual(imported.count,1)
        let reviews = CharacterReviewStore(root: root.appendingPathComponent("reviews"))
        try await reviews.record(id:"synthetic-test",referenceHash:hash,generatedHash:String(repeating:"b",count:64),decision:.matches,categories:["Test"])
        let savedReview = try await reviews.latest(id:"synthetic-test",referenceHash:hash)
        XCTAssertEqual(savedReview?.decision,.matches)
        let changedReview = try await reviews.latest(id:"synthetic-test",referenceHash:String(repeating:"c",count:64))
        XCTAssertNil(changedReview)
        try Data("damaged".utf8).write(to: voice.appendingPathComponent("reference.wav"))
        do { _ = try await store.importCollection(at:collection); XCTFail("Corrupt refresh must fail") } catch {}
        let unchanged = try await store.profiles(); XCTAssertEqual(unchanged,imported)
        try fm.removeItem(at:collection)
        let cached = try await store.referenceURL(id:"synthetic-test")
        XCTAssertEqual(try Data(contentsOf:cached),wav)
        let reloaded = CharacterFolderStore(root:root.appendingPathComponent("private"))
        let persisted = try await reloaded.profiles(); XCTAssertEqual(persisted,imported)
    }
}
