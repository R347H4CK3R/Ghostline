import Foundation
import CryptoKit

/// Every selected asset is pinned. Unlisted files (including an optional CTC model)
/// are rejected before FluidAudio can discover/load them. No runtime downloader.
enum BundledASRAssets {
    static let revision = "7dd20fe6b1797d35f5e3307e8b1732d9a178edfe"
    static let lockSHA256 = "9916ff1ec288709815d015d9201885087e4d12e54f94740daee6e21caddff7a8"
    struct Lock: Decodable {
        struct File: Decodable { let size: Int; let sha256: String }
        let schemaVersion: Int
        let repository: String
        let revision: String
        let files: [String: File]
    }
    enum Failure: LocalizedError {
        case missing, invalid
        var errorDescription: String? {
            switch self {
            case .missing: return "Bundled speech recognition is missing. Install a complete standalone build. No audio was sent to a server."
            case .invalid: return "Bundled speech recognition failed its integrity check. Your source and existing voices were retained."
            }
        }
    }
    static func manifest(at root: URL) throws -> Lock {
        try Task.checkCancellation()
        guard root.isFileURL else { throw Failure.invalid }
        let values = try root.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true else { throw Failure.invalid }
        let url = root.appendingPathComponent("resource-lock.json")
        let v = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard v.isRegularFile == true, v.isSymbolicLink != true, let size = v.fileSize, (1...65_536).contains(size) else { throw Failure.invalid }
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        let data = try handle.read(upToCount: 65_537) ?? Data()
        guard data.count == size, hex(SHA256.hash(data: data)) == lockSHA256 else { throw Failure.invalid }
        let lock = try JSONDecoder().decode(Lock.self, from: data)
        guard lock.schemaVersion == 1, lock.repository == "FluidInference/parakeet-tdt-0.6b-v3-coreml",
              lock.revision == revision, lock.files.count == 20 else { throw Failure.invalid }
        return lock
    }
    static func verify(_ root: URL) throws {
        let lock = try manifest(at: root)
        var scanFailed = false
        guard let enumeration = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey], errorHandler: { _, _ in scanFailed = true; return false }) else { throw Failure.invalid }
        var observed = Set<String>()
        while let url = enumeration.nextObject() as? URL {
            try Task.checkCancellation()
            let v = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard v.isSymbolicLink != true else { throw Failure.invalid }
            if v.isRegularFile == true {
                let name = String(url.path.dropFirst(root.path.count + 1))
                if name == "resource-lock.json" { continue }
                if name == ".gitkeep", v.fileSize == 0 { continue }
                guard lock.files[name] != nil else { throw Failure.invalid }
                observed.insert(name)
            }
        }
        guard !scanFailed, observed == Set(lock.files.keys) else { throw Failure.invalid }
        for (name, expected) in lock.files {
            try Task.checkCancellation()
            let parts = name.split(separator: "/", omittingEmptySubsequences: false)
            guard !name.contains("\\"), parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }),
                  (1...650_000_000).contains(expected.size) else { throw Failure.invalid }
            var url = root
            for part in parts {
                url.appendPathComponent(String(part))
                guard try url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink != true else { throw Failure.invalid }
            }
            let v = try url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            guard v.isRegularFile == true, v.fileSize == expected.size else { throw Failure.invalid }
            let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
            var hash = SHA256(), bytesRead = 0
            while let bytes = try handle.read(upToCount: 1_048_576), !bytes.isEmpty {
                try Task.checkCancellation(); bytesRead += bytes.count
                guard bytesRead <= expected.size else { throw Failure.invalid }
                hash.update(data: bytes)
            }
            guard bytesRead == expected.size, hex(hash.finalize()) == expected.sha256 else { throw Failure.invalid }
        }
    }
    private static func hex<S: Sequence>(_ bytes: S) -> String where S.Element == UInt8 {
        bytes.map { String(format: "%02x", $0) }.joined()
    }
}
