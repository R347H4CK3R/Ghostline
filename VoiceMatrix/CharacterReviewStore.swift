import Foundation

enum CharacterReviewError: Error { case invalidRecord, damagedHistory }
enum CharacterMatchDecision: String, Codable { case matches, different, unsure }
struct CharacterListeningReview: Codable, Identifiable {
    let id: UUID
    let characterID, referenceSHA256, generatedSHA256: String
    let decision: CharacterMatchDecision
    let categories: [String]
    let createdAt: Date
    let reviewer: String
}

// Listening feedback is separate from native inference and intelligibility checks.
// Exact reference hashes prevent new recordings from inheriting an old approval.
actor CharacterReviewStore {
    private let root: URL
    init(root: URL) { self.root = root }
    private func safeID(_ id: String) -> Bool { id.range(of: "^[a-z0-9_-]{1,100}$", options: .regularExpression) != nil }
    private func digest(_ value: String) -> Bool { value.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil }
    func history(id: String) throws -> [CharacterListeningReview] {
        guard safeID(id) else { throw CharacterReviewError.invalidRecord }
        let url = root.appendingPathComponent(id).appendingPathExtension("json")
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let bytes = values.fileSize, bytes <= 2_000_000 else { throw CharacterReviewError.damagedHistory }
        let rows = try JSONDecoder().decode([CharacterListeningReview].self, from: Data(contentsOf: url))
        guard rows.allSatisfy({ $0.characterID == id && digest($0.referenceSHA256) && digest($0.generatedSHA256) }) else { throw CharacterReviewError.damagedHistory }
        return rows
    }
    func latest(id: String, referenceHash: String) throws -> CharacterListeningReview? {
        guard digest(referenceHash) else { throw CharacterReviewError.invalidRecord }
        return try history(id: id).last(where: { $0.referenceSHA256 == referenceHash })
    }
    func record(id: String, referenceHash: String, generatedHash: String, decision: CharacterMatchDecision, categories: [String]) throws {
        guard safeID(id), digest(referenceHash), digest(generatedHash), !categories.isEmpty,
              categories.count <= 50, Set(categories).count == categories.count,
              categories.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else { throw CharacterReviewError.invalidRecord }
        var rows = try history(id: id)
        rows.append(CharacterListeningReview(id: UUID(), characterID: id, referenceSHA256: referenceHash, generatedSHA256: generatedHash, decision: decision, categories: categories, createdAt: Date(), reviewer: "On-device listener"))
        let data = try JSONEncoder().encode(rows)
        guard data.count <= 2_000_000 else { throw CharacterReviewError.damagedHistory }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try data.write(to: root.appendingPathComponent(id).appendingPathExtension("json"), options: .atomic)
    }
}
