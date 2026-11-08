import Foundation
import CryptoKit

@main struct CharacterFolderChecks {
    static func expectFailure(_ operation: () async throws -> Void) async throws {
        var failed = false
        do { try await operation() } catch { failed = true }
        precondition(failed, "Invalid import unexpectedly succeeded")
    }
    static func main() async throws {
        let fm = FileManager.default
        let input = URL(fileURLWithPath: CommandLine.arguments[1])
        let work = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: work) }
        try fm.createDirectory(at: work, withIntermediateDirectories: true)
        let store = CharacterFolderStore(root: work.appendingPathComponent("private"))
        let original = try await store.importCollection(at: input)
        precondition(original.count == 1 && original[0].id == "original-test")
        precondition(original[0].categories == ["Animation", "Fantasy"])
        let cached = try await store.referenceURL(id: "original-test")
        precondition(cached.path.hasPrefix(work.path))
        let cachedBytes = try Data(contentsOf: cached)
        let updated = work.appendingPathComponent("updated")
        try fm.copyItem(at: input, to: updated)
        let manifest = updated.appendingPathComponent("original-test/manifest.json")
        var metadata = try JSONSerialization.jsonObject(with: Data(contentsOf: manifest)) as! [String: Any]
        metadata["name"] = "Updated Original"
        try JSONSerialization.data(withJSONObject: metadata).write(to: manifest)
        let revised = try await store.importCollection(at: updated)
        precondition(revised.count == 1 && revised[0].name == "Updated Original")
        // Valid new conditioning must not replace the active voice on refresh.
        let changedText = work.appendingPathComponent("changed-text")
        try fm.copyItem(at: updated, to: changedText)
        let changedManifest = changedText.appendingPathComponent("original-test/manifest.json")
        var changedMetadata = try JSONSerialization.jsonObject(with: Data(contentsOf: changedManifest)) as! [String: Any]
        changedMetadata["referenceText"] = "Different conditioning words."
        try JSONSerialization.data(withJSONObject: changedMetadata).write(to: changedManifest)
        try await expectFailure { _ = try await store.importCollection(at: changedText) }
        let retained = try await store.profiles()
        precondition(retained == revised, "Unreviewed conditioning replaced the active reference")
        let changedAudioFolder = work.appendingPathComponent("changed-audio")
        try fm.copyItem(at: input, to: changedAudioFolder)
        let changedAudioURL = changedAudioFolder.appendingPathComponent("original-test/reference.wav")
        var changedAudio = try Data(contentsOf: changedAudioURL)
        changedAudio[44] ^= 1
        try changedAudio.write(to: changedAudioURL)
        let audioManifest = changedAudioFolder.appendingPathComponent("original-test/manifest.json")
        var audioMetadata = try JSONSerialization.jsonObject(with: Data(contentsOf: audioManifest)) as! [String: Any]
        audioMetadata["referenceSHA256"] = SHA256.hash(data: changedAudio).map { String(format: "%02x", $0) }.joined()
        try JSONSerialization.data(withJSONObject: audioMetadata).write(to: audioManifest)
        try await expectFailure { _ = try await store.importCollection(at: changedAudioFolder) }
        let unchangedActive = try await store.profiles()
        precondition(unchangedActive == revised)
        let unchangedURL = try await store.referenceURL(id: "original-test")
        let unchangedBytes = try Data(contentsOf: unchangedURL)
        precondition(unchangedBytes == cachedBytes)
        // A valid addition earlier in the same batch cannot leak into the active
        // library when a later entry attempts to replace conditioning.
        let mixed = work.appendingPathComponent("mixed")
        try fm.copyItem(at: changedText, to: mixed)
        let addition = mixed.appendingPathComponent("new-test")
        try fm.copyItem(at: changedAudioFolder.appendingPathComponent("original-test"), to: addition)
        let additionManifest = addition.appendingPathComponent("manifest.json")
        var additionMetadata = try JSONSerialization.jsonObject(with: Data(contentsOf: additionManifest)) as! [String: Any]
        additionMetadata["id"] = "new-test"
        try JSONSerialization.data(withJSONObject: additionMetadata).write(to: additionManifest)
        try JSONSerialization.data(withJSONObject: ["schemaVersion":1,"voices":[["id":"new-test","folder":"new-test"],["id":"original-test","folder":"original-test"]]]).write(to: mixed.appendingPathComponent("collection.json"))
        try await expectFailure { _ = try await store.importCollection(at: mixed) }
        let afterMixedBatch = try await store.profiles()
        precondition(afterMixedBatch == revised, "A rejected batch partially changed the active library")
        // A later corrupt refresh must not replace a usable private revision.
        try Data("broken".utf8).write(to: updated.appendingPathComponent("original-test/reference.wav"))
        try await expectFailure { _ = try await store.importCollection(at: updated) }
        let afterCorruption = try await store.profiles()
        precondition(afterCorruption == revised)
        try fm.removeItem(at: updated)
        let offlineReference = try await store.referenceURL(id: "original-test")
        let offlineBytes = try Data(contentsOf: offlineReference)
        precondition(offlineBytes == cachedBytes)
        // Duplicate IDs, path traversal and linked source bytes are rejected.
        try fm.copyItem(at: input, to: updated)
        let index = updated.appendingPathComponent("collection.json")
        let entry: [String: String] = ["id":"original-test", "folder":"original-test"]
        try JSONSerialization.data(withJSONObject: ["schemaVersion":1,"voices":[entry,entry]]).write(to: index)
        try await expectFailure { _ = try await store.importCollection(at: updated) }
        try JSONSerialization.data(withJSONObject: ["schemaVersion":1,"voices":[["id":"original-test","folder":"../original-test"]]]).write(to: index)
        try await expectFailure { _ = try await store.importCollection(at: updated) }
        try fm.removeItem(at: updated)
        try fm.copyItem(at: input, to: updated)
        let wav = updated.appendingPathComponent("original-test/reference.wav")
        try fm.removeItem(at: wav)
        try fm.createSymbolicLink(at: wav, withDestinationURL: cached)
        try await expectFailure { _ = try await store.importCollection(at: updated) }
        let afterInvalidImports = try await store.profiles()
        precondition(afterInvalidImports == revised)
        print("Native folder checks passed: import, private offline copy, revision update, atomic rollback, duplicate IDs, traversal and symlink rejection")
    }
}
