import Foundation
import CryptoKit

enum VoiceFolderSync {
    private struct Catalog: Decodable {
        struct File: Decodable { let path, sha256: String; let bytes: Int }
        let schemaVersion: Int
        let revision: String
        let files: [File]
    }
    static func bounded<T: Sendable>(seconds: Double = 120, onTimeout: @escaping @Sendable () -> Void, operation: @escaping @Sendable () async throws -> T) async throws -> T {
        let started = ContinuousClock.now
        return try await withThrowingTaskGroup(of: T.self) { group in
            group.addTask { try await operation() }
            group.addTask {
                try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
                onTimeout()
                throw invalid()
            }
            defer { group.cancelAll() }
            guard let result = try await group.next(), started.duration(to: .now) < .seconds(seconds) else { throw invalid() }
            return result
        }
    }
    static func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private static func invalid() -> NSError { NSError(domain: "VoiceMatrix.Sync", code: 1, userInfo: [NSLocalizedDescriptionKey: "The laptop voice snapshot changed or failed validation. Your saved voices were kept."]) }
    static func download(to folder: URL, previousRevision: String?, progress: @Sendable (VoiceSyncProgress) async -> Void = { _ in }, fetch: (String, Int) async throws -> Data) async throws -> String? {
        let data = try await fetch("voices", 1_048_576)
        guard data.count <= 1_048_576 else { throw invalid() }
        let catalog = try JSONDecoder().decode(Catalog.self, from: data)
        guard catalog.schemaVersion == 1, (3...2001).contains(catalog.files.count), Set(catalog.files.map(\.path)).count == catalog.files.count else { throw invalid() }
        var total = 0, paths = Set<String>(), ids = Set<String>()
        for file in catalog.files {
            guard file.sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil, file.bytes > 0 else { throw invalid() }
            if file.path == "collection.json" {
                guard file.bytes <= 256000 else { throw invalid() }
            } else {
                let parts = file.path.split(separator: "/", omittingEmptySubsequences: false)
                guard parts.count == 2, parts[0].range(of: "^[a-z0-9_-]{1,100}$", options: .regularExpression) != nil,
                      parts[1] == "manifest.json" || parts[1] == "reference.wav",
                      file.bytes <= (parts[1] == "manifest.json" ? 65536 : 848000) else { throw invalid() }
                ids.insert(String(parts[0]))
            }
            paths.insert(file.path); total += file.bytes
            guard total <= 67_108_864 else { throw invalid() }
        }
        guard paths.contains("collection.json"), ids.allSatisfy({ paths.contains($0 + "/manifest.json") && paths.contains($0 + "/reference.wav") }) else { throw invalid() }
        let proof = catalog.files.sorted { $0.path < $1.path }.map { $0.path + ":" + $0.sha256 + ":" + String($0.bytes) + "\n" }.joined()
        guard digest(Data(proof.utf8)) == catalog.revision else { throw invalid() }
        await progress(.catalogValidated(catalog.files.count, total))
        if previousRevision == catalog.revision { return nil }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        for (index, file) in catalog.files.enumerated() {
            try Task.checkCancellation()
            await progress(.downloading(index + 1, catalog.files.count))
            let bytes = try await fetch("voices/" + catalog.revision + "/" + file.path, file.bytes)
            guard bytes.count == file.bytes, digest(bytes) == file.sha256 else { throw invalid() }
            let destination = folder.appendingPathComponent(file.path)
            try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try bytes.write(to: destination, options: .atomic)
            await progress(.fileValidated(index + 1, catalog.files.count))
        }
        try Task.checkCancellation()
        return catalog.revision
    }
}
