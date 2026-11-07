import Foundation
@main struct CharacterCatalogChecks {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let manifest = try JSONDecoder().decode(VoiceManifest.self, from: data)
        precondition(manifest.voices.count == 537)
        precondition(manifest.voices.filter { $0.libraryGroup == "Replicas" }.isEmpty)
        precondition(manifest.voices.filter { $0.libraryGroup == "Character styles" }.count == 12)
        precondition(manifest.voices.filter { $0.libraryGroup == "Other speakers" }.count == 525)
        for voice in manifest.voices { try voice.characterIdentity?.validate() }
        let valid = CharacterIdentity(kind: "authorizedReplica", targetName: "Fixture character", franchise: "Test only", genres: ["Horror & Monsters", "Movies & Television"], referenceSHA256: [String(repeating: "a", count: 64)], authorizationRecord: "models/authorizations/fixture.json")
        try valid.validate()
        let bad = [
            CharacterIdentity(kind: "replica", targetName: "Fixture", franchise: nil, genres: ["Horror & Monsters"], referenceSHA256: [], authorizationRecord: nil),
            CharacterIdentity(kind: "authorizedReplica", targetName: "", franchise: nil, genres: ["Horror & Monsters"], referenceSHA256: valid.referenceSHA256, authorizationRecord: valid.authorizationRecord),
            CharacterIdentity(kind: "authorizedReplica", targetName: "Fixture", franchise: nil, genres: ["Horror & Monsters"], referenceSHA256: [], authorizationRecord: valid.authorizationRecord),
            CharacterIdentity(kind: "authorizedReplica", targetName: "Fixture", franchise: nil, genres: ["Horror & Monsters"], referenceSHA256: ["not-a-hash"], authorizationRecord: valid.authorizationRecord),
            CharacterIdentity(kind: "authorizedReplica", targetName: "Fixture", franchise: nil, genres: ["Horror & Monsters"], referenceSHA256: valid.referenceSHA256, authorizationRecord: nil),
            CharacterIdentity(kind: "authorizedReplica", targetName: "Fixture", franchise: nil, genres: ["Horror & Monsters"], referenceSHA256: valid.referenceSHA256, authorizationRecord: "models/authorizations/../fixture.json"),
            CharacterIdentity(kind: "characterInspired", targetName: "Fixture", franchise: nil, genres: ["Invented genre"], referenceSHA256: [], authorizationRecord: nil)
        ]
        for value in bad {
            do { try value.validate(); fatalError("Invalid identity accepted") } catch StudioError.invalidAsset { }
        }
        var object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(manifest.voices[0])) as! [String: Any]
        object["characterIdentity"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(valid))
        let replica = try JSONDecoder().decode(VoiceProfile.self, from: JSONSerialization.data(withJSONObject: object))
        precondition(replica.libraryGroup == "Replicas")
        precondition(replica.searchText.contains("Fixture character") && replica.searchText.contains("Test only"))
        precondition(replica.matchesCategory("Horror & Monsters"))
        precondition(replica.identityLabel.contains("resemblance unverified"))
        precondition(Set(replica.allCategories).count == replica.allCategories.count)
        print("Character catalog checks passed: legacy537, character12, replica0; invalid identity rejection and target/franchise/category search.")
    }
}
