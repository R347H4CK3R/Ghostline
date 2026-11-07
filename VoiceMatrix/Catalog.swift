import Foundation
import CryptoKit

struct VoiceProfile: Codable, Identifiable, Hashable {
    let id, name, category, language, accent, path, sha256, engine, source, permissions, qualityStatus: String
    let size: Int
    let deviceVerified: Bool
    var description: String { "\(accent) • \(category)" }
}
struct AssetRecord: Codable { let path, sha256: String; let size: Int }
struct VoiceManifest: Codable {
    let schemaVersion: Int
    let engine, revision: String
    let files: [AssetRecord]
    let voices: [VoiceProfile]
}
enum StudioError: LocalizedError {
    case missingPack, invalidAsset(String), emptyAudio, busy
    var errorDescription: String? {
        switch self {
        case .missingPack: return "The included voices are missing. Reinstall the complete VoiceMatrix build."
        case .invalidAsset(let name): return "An included voice file is damaged (\(name)). Reinstall the app."
        case .emptyAudio: return "That voice did not produce usable audio. Try a shorter message or another voice."
        case .busy: return "Please stop the current recording or speech first."
        }
    }
}
enum Catalog {
    static func read() throws -> (URL, VoiceManifest) {
        guard let root = Bundle.main.url(forResource: "Phonon", withExtension: nil) else { throw StudioError.missingPack }
        let manifest = try JSONDecoder().decode(VoiceManifest.self, from: Data(contentsOf: root.appendingPathComponent("manifest.json")))
        guard manifest.schemaVersion == 1, manifest.engine == "phonon31m", !manifest.voices.isEmpty,
              Set(manifest.voices.map(\.id)).count == manifest.voices.count,
              Set(manifest.voices.map(\.sha256)).count == manifest.voices.count else { throw StudioError.invalidAsset("catalog") }
        return (root, manifest)
    }
    static func validate(root: URL, manifest: VoiceManifest) throws {
        try validateAssets(root: root, files: manifest.files)
        for voice in manifest.voices {
            guard manifest.files.contains(where: { $0.path == voice.path && $0.sha256 == voice.sha256 && $0.size == voice.size }) else { throw StudioError.invalidAsset(voice.name) }
        }
    }
    static func validateAssets(root: URL, files: [AssetRecord]) throws {
        var seen = Set<String>()
        for entry in files {
            guard !entry.path.hasPrefix("/"), !entry.path.split(separator: "/").contains(".."), seen.insert(entry.path).inserted else { throw StudioError.invalidAsset("catalog path") }
            let url = root.appendingPathComponent(entry.path)
            let handle = try FileHandle(forReadingFrom: url)
            defer { try? handle.close() }
            var hash = SHA256(); var bytes = 0
            while let chunk = try handle.read(upToCount: 1_048_576), !chunk.isEmpty { hash.update(data: chunk); bytes += chunk.count }
            let digest = hash.finalize().map { String(format: "%02x", $0) }.joined()
            guard bytes == entry.size, digest == entry.sha256 else { throw StudioError.invalidAsset(entry.path) }
        }
    }

}
