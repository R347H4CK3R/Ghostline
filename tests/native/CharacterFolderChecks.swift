import Foundation

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
