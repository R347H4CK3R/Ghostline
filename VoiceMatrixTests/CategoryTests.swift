import XCTest
@testable import VoiceMatrix
final class CategoryTests: XCTestCase {
    private func voice() throws -> VoiceProfile {
        let object: [String: Any] = ["id": "original", "name": "Original Ogre", "category": "Fantasy & Characters", "language": "en", "accent": "Character performance", "path": "voices/original", "sha256": "hash", "engine": "phonon31m", "source": "licensed", "permissions": "source terms", "qualityStatus": "pending", "size": 1, "deviceVerified": false, "categories": ["Fantasy & Characters", "Horror & Monsters", "Horror & Monsters"]]
        return try JSONDecoder().decode(VoiceProfile.self, from: JSONSerialization.data(withJSONObject: object))
    }
    func testOneProfileMatchesOverlappingGenresWithoutDuplicateRowsOrFiles() throws {
        let original = try voice()
        XCTAssertTrue(original.matchesCategory("Horror & Monsters"))
        XCTAssertTrue(original.matchesCategory("Fantasy & Characters"))
        XCTAssertEqual(original.allCategories.count, 2)
        XCTAssertEqual([original].filter { $0.matchesCategory("Horror & Monsters") }.count, 1)
        XCTAssertEqual(original.path, "voices/original")
    }
    func testSearchIncludesCategories() throws {
        let original = try voice()
        XCTAssertTrue(original.searchText.localizedCaseInsensitiveContains("horror"))
        XCTAssertFalse(original.matchesCategory("Studio Voices"))
    }
}
