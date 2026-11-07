import Foundation
import CryptoKit

struct VoiceProfile: Codable, Identifiable, Hashable {
    let id, name, category, language, accent, path, sha256, engine, source, permissions, qualityStatus: String
    let size: Int
    let deviceVerified: Bool
    let baseVoiceID: String?
    let usageRestriction: String?
    let categories: [String]?
    let characterIdentity: CharacterIdentity?
    var libraryGroup: String {
        if characterIdentity?.kind == "authorizedReplica" { return "Replicas" }
        if characterIdentity?.kind == "characterInspired" || id.hasPrefix("characters_") { return "Character styles" }
        return "Other speakers"
    }
    var identityLabel: String {
        if let identity = characterIdentity {
            return identity.kind == "authorizedReplica" ? "Authorized replica of \(identity.targetName) · resemblance unverified" : "Original voice inspired by \(identity.targetName) · not an official replica"
        }
        return libraryGroup == "Character styles" ? "Original character performance · not a named-character replica" : "General speaker · not a character replica"
    }
    var description: String { "\(accent) • \(category)" + (usageRestriction.map { " • " + $0 } ?? "") }
    var allCategories: [String] { Array(Set((categories ?? []) + [category] + (characterIdentity?.genres ?? []))).sorted() }
    var searchText: String { ([name, category, accent, characterIdentity?.targetName ?? "", characterIdentity?.franchise ?? ""] + allCategories).joined(separator: " ") }
    func matchesCategory(_ selected: String) -> Bool { allCategories.contains(selected) }
}
struct CharacterIdentity: Codable, Hashable {
    let kind, targetName: String
    let franchise: String?
    let genres: [String]
    let referenceSHA256: [String]
    let authorizationRecord: String?
    static let allowedGenres = ["Animation & Cartoons", "Horror & Monsters", "Movies & Television", "Video Games", "Anime & Fantasy", "Science Fiction & Superheroes", "Original & Comedy"]
    func validate() throws {
        guard ["authorizedReplica", "characterInspired"].contains(kind),
              !targetName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !genres.isEmpty, Set(genres).count == genres.count,
              genres.allSatisfy({ Self.allowedGenres.contains($0) }) else { throw StudioError.invalidAsset("character identity") }
        if kind == "authorizedReplica" {
            guard let record = authorizationRecord, record.hasPrefix("models/authorizations/"),
                  !record.split(separator: "/").contains(".."),
                  !referenceSHA256.isEmpty, Set(referenceSHA256).count == referenceSHA256.count,
                  referenceSHA256.allSatisfy({ $0.count == 64 && $0.allSatisfy({ "0123456789abcdef".contains($0) }) })
            else { throw StudioError.invalidAsset("replica reference records") }
        }
    }
}
struct AssetRecord: Codable { let path, sha256: String; let size: Int }
struct VoiceManifest: Codable {
    let schemaVersion: Int
    let engine, revision: String
    let files: [AssetRecord]
    let voices: [VoiceProfile]
}
enum StudioError: LocalizedError {
    case missingPack, invalidAsset(String), emptyAudio, busy, textTooLongForVoice
    var errorDescription: String? {
        switch self {
        case .missingPack: return "The included voices are missing. Reinstall the complete VoiceMatrix build."
        case .invalidAsset(let name): return "An included voice file is damaged (\(name)). Reinstall the app."
        case .emptyAudio: return "That voice did not produce usable audio. Try a shorter message or another voice."
        case .textTooLongForVoice: return "That message needs shorter sentences for this voice. Shorten it or try another voice."
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
        for voice in manifest.voices {
            try voice.characterIdentity?.validate()
            guard ["phonon31m", "phonon31m-openvoicev2"].contains(voice.engine) else { throw StudioError.invalidAsset("voice engine") }
            if voice.engine == "phonon31m-openvoicev2" {
                guard let base = voice.baseVoiceID, manifest.voices.contains(where: { $0.id == base && $0.engine == "phonon31m" }) else { throw StudioError.invalidAsset("voice source") }
            }
        }
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
