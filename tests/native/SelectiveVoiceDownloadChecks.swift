import Foundation

@main struct SelectiveVoiceDownloadChecks {
    static func reject(_ operation: () async throws -> Void) async throws {
        var rejected = false
        do { try await operation() } catch { rejected = true }
        precondition(rejected, "Unsafe selective download accepted")
    }
    static func main() async throws {
        let fm = FileManager.default
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let source = URL(fileURLWithPath: CommandLine.arguments[2])
        let work = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: work) }
        let catalog = try RemoteVoiceCatalog.decode(data)
        precondition(catalog.voices.count == 2)
        var calls: [String] = []
        func fetch(_ path: String, _ limit: Int) async throws -> Data {
            calls.append(path)
            let prefix = "voices/" + catalog.revision + "/"
            precondition(path.hasPrefix(prefix))
            let bytes = try Data(contentsOf: source.appendingPathComponent(String(path.dropFirst(prefix.count))))
            precondition(bytes.count <= limit)
            return bytes
        }
        let first = work.appendingPathComponent("first")
        try await catalog.download(id: "voice-0", to: first, fetch: fetch)
        precondition(calls == ["voices/" + catalog.revision + "/voice-0/manifest.json", "voices/" + catalog.revision + "/voice-0/reference.wav"])
        precondition(!fm.fileExists(atPath: first.appendingPathComponent("voice-1").path))
        let store = CharacterFolderStore(root: work.appendingPathComponent("saved"))
        let saved = try await store.importCollection(at: first)
        precondition(saved.map(\.id) == ["voice-0"])
        let bytes = try await store.storedBytes()
        precondition(bytes > Int64(saved[0].referenceBytes))
        calls = []
        let second = work.appendingPathComponent("second")
        try await catalog.download(id: "voice-1", to: second, fetch: fetch)
        let combined = try await store.importCollection(at: second)
        precondition(Set(combined.map(\.id)) == ["voice-0", "voice-1"])
        precondition(calls.count == 2)
        try await reject { try await catalog.download(id: "../outside", to: work.appendingPathComponent("unsafe"), fetch: fetch) }
        let bad = work.appendingPathComponent("bad")
        try await reject {
            try await catalog.download(id: "voice-1", to: bad) { path, limit in Data("corrupted".utf8) }
        }
        precondition(!fm.fileExists(atPath: bad.appendingPathComponent("collection.json").path))
        try await reject {
            try await catalog.download(id: "voice-1", to: work.appendingPathComponent("cancel")) { path, limit in throw CancellationError() }
        }
        let retained = try await store.profiles()
        precondition(retained == combined)
        var changed = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        var voices = changed["voices"] as! [[String: Any]]
        voices[0]["referenceText"] = "A tampered transcript."
        changed["voices"] = voices
        let tampered = try RemoteVoiceCatalog.decode(JSONSerialization.data(withJSONObject: changed))
        try await reject { try await tampered.download(id: "voice-0", to: work.appendingPathComponent("tampered"), fetch: fetch) }
        changed["voices"] = [voices[0], voices[0]]
        try await reject { _ = try RemoteVoiceCatalog.decode(JSONSerialization.data(withJSONObject: changed)) }
        changed.removeValue(forKey: "voices")
        try await reject { _ = try RemoteVoiceCatalog.decode(JSONSerialization.data(withJSONObject: changed)) }
        try await reject { _ = try RemoteVoiceCatalog.decode(Data(repeating: 0, count: RemoteVoiceCatalog.byteLimit + 1)) }
        let cache = RemoteVoiceCatalogCache(file: work.appendingPathComponent("cache/catalog.json"))
        let date = Date(timeIntervalSince1970: 1000)
        try await cache.save(catalog, checkedAt: date)
        let cached = try await cache.load()
        precondition(cached?.catalog.voices == catalog.voices && cached?.checkedAt == date)
        // Catalog failure must not modify the last valid cached index or any imported reference.
        let cachedAgain = try await cache.load()
        precondition(cachedAgain?.catalog.revision == catalog.revision)
        print("Selective voice download checks passed")
    }
}
