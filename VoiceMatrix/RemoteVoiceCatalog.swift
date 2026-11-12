import Foundation

/// Metadata only. Character audio enters the private library only after an explicit download.
struct RemoteVoiceCatalog: Codable, Sendable {
    struct File: Codable, Sendable { let path, sha256: String; let bytes: Int }
    static let byteLimit = 1_048_576
    let schemaVersion: Int
    let revision: String
    let files: [File]
    let voices: [CharacterReference]

    static func invalid() -> NSError {
        NSError(domain: "VoiceMatrix.Catalog", code: 1, userInfo: [NSLocalizedDescriptionKey: "The laptop catalog is unavailable or changed. Update the companion and refresh. Your downloaded voices were kept."])
    }
    static func decode(_ data: Data) throws -> Self {
        guard data.count <= byteLimit else { throw invalid() }
        let result = try JSONDecoder().decode(Self.self, from: data)
        try result.validate()
        return result
    }
    func validate() throws {
        guard schemaVersion == 1, (1...1000).contains(voices.count), files.count == voices.count * 2 + 1,
              Set(voices.map(\.id)).count == voices.count, Set(files.map(\.path)).count == files.count,
              Set(voices.map(\.referenceSHA256)).count == voices.count else { throw Self.invalid() }
        var total = 0
        let ids = Set(voices.map(\.id))
        for file in files {
            guard file.bytes > 0, file.sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else { throw Self.invalid() }
            if file.path == "collection.json" {
                guard file.bytes <= 256000 else { throw Self.invalid() }
            } else {
                let parts = file.path.split(separator: "/", omittingEmptySubsequences: false)
                guard parts.count == 2, ids.contains(String(parts[0])),
                      ["manifest.json", "reference.wav"].contains(String(parts[1])),
                      file.bytes <= (parts[1] == "manifest.json" ? 65536 : 848000) else { throw Self.invalid() }
            }
            total += file.bytes
            guard total <= 67_108_864 else { throw Self.invalid() }
        }
        guard files.contains(where: { $0.path == "collection.json" }) else { throw Self.invalid() }
        for voice in voices {
            guard voice.id.range(of: "^[a-z0-9_-]{1,100}$", options: .regularExpression) != nil,
                  voice.schemaVersion == 1, voice.kind == "f5-reference", voice.engine == "F5TTS_v1_Base", !voice.trainedModel,
                  voice.referenceFile == "reference.wav", (0.5...15).contains(voice.seconds),
                  [voice.name, voice.source, voice.permission, voice.referenceText].allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
                  (1...50).contains(voice.categories.count), Set(voice.categories).count == voice.categories.count,
                  voice.categories.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
                  files.contains(where: { $0.path == voice.id + "/manifest.json" }),
                  files.contains(where: { $0.path == voice.id + "/reference.wav" && $0.bytes == voice.referenceBytes && $0.sha256 == voice.referenceSHA256 }) else { throw Self.invalid() }
        }
        let proof = files.sorted { $0.path < $1.path }.map { $0.path + ":" + $0.sha256 + ":" + String($0.bytes) + "\n" }.joined()
        guard VoiceFolderSync.digest(Data(proof.utf8)) == revision else { throw Self.invalid() }
    }
    func downloadBytes(id: String) -> Int { files.filter { $0.path.hasPrefix(id + "/") }.reduce(0) { $0 + $1.bytes } }

    func download(id: String, to folder: URL, progress: @Sendable (VoiceSyncProgress) async -> Void = { _ in }, fetch: (String, Int) async throws -> Data) async throws {
        try validate()
        guard let voice = voices.first(where: { $0.id == id }) else { throw Self.invalid() }
        let selected = files.filter { $0.path.hasPrefix(id + "/") }.sorted { $0.path < $1.path }
        guard selected.count == 2 else { throw Self.invalid() }
        try Task.checkCancellation()
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        for (index, file) in selected.enumerated() {
            try Task.checkCancellation()
            await progress(.downloading(index + 1, selected.count))
            let bytes = try await fetch("voices/" + revision + "/" + file.path, file.bytes)
            try Task.checkCancellation()
            guard bytes.count == file.bytes, VoiceFolderSync.digest(bytes) == file.sha256 else { throw Self.invalid() }
            if file.path.hasSuffix("/manifest.json") {
                guard try JSONDecoder().decode(CharacterReference.self, from: bytes) == voice else { throw Self.invalid() }
            }
            let destination = folder.appendingPathComponent(file.path)
            try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try bytes.write(to: destination, options: .atomic)
            await progress(.fileValidated(index + 1, selected.count))
        }
        try Task.checkCancellation()
        // The original all-voice collection is deliberately not downloaded or imported.
        let collection: [String: Any] = ["schemaVersion": 1, "voices": [["id": id, "folder": id]]]
        try JSONSerialization.data(withJSONObject: collection).write(to: folder.appendingPathComponent("collection.json"), options: .atomic)
    }
}

actor RemoteVoiceCatalogCache {
    struct Snapshot: Codable, Sendable { let catalog: RemoteVoiceCatalog; let checkedAt: Date }
    private let file: URL
    init(file: URL) { self.file = file }
    func load() throws -> Snapshot? {
        guard FileManager.default.fileExists(atPath: file.path) else { return nil }
        let values = try file.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size = values.fileSize, size <= RemoteVoiceCatalog.byteLimit + 4096 else { throw RemoteVoiceCatalog.invalid() }
        let snapshot = try JSONDecoder().decode(Snapshot.self, from: Data(contentsOf: file))
        try snapshot.catalog.validate()
        return snapshot
    }
    func save(_ catalog: RemoteVoiceCatalog, checkedAt: Date) throws {
        try catalog.validate()
        let data = try JSONEncoder().encode(Snapshot(catalog: catalog, checkedAt: checkedAt))
        guard data.count <= RemoteVoiceCatalog.byteLimit + 4096 else { throw RemoteVoiceCatalog.invalid() }
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: file, options: .atomic)
    }
}
