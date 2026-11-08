import XCTest
@testable import VoiceMatrix

final class AppUpdateTests: XCTestCase {
    private func feed(_ versions: [[String: Any]], bundle: String = "com.voicematrix.app") throws -> Data {
        try JSONSerialization.data(withJSONObject: ["apps": [["bundleIdentifier": bundle, "versions": versions]]])
    }
    private func item(_ version: String, _ build: String = "1", url: String = "https://github.com/R347H4CK3R/Ghostline/releases/download/test/VoiceMatrix.ipa") -> [String: Any] {
        ["version": version, "buildVersion": build, "downloadURL": url, "size": 1234, "minOSVersion": "26.0"]
    }
    func testNumericOrderingAndBuildUpdates() throws {
        let data = try feed([item("0.9.0"), item("0.10.0"), item("0.4.3", "2")])
        XCTAssertEqual(try UpdateCatalog.latest(data, installedVersion: "0.4.3", installedBuild: "1")?.version, "0.10.0")
        XCTAssertEqual(try UpdateCatalog.latest(feed([item("0.4.3", "2")]), installedVersion: "0.4.3", installedBuild: "1")?.build, "2")
        XCTAssertEqual(UpdateCatalog.compare("1.0", "1.0.0"), .orderedSame)
    }
    func testNoDowngradeOrSameBuildOffer() throws {
        XCTAssertNil(try UpdateCatalog.latest(feed([item("0.4.1"), item("0.4.3")]), installedVersion: "0.4.3", installedBuild: "1"))
    }
    func testWrongBundleAndMalformedVersionsFailClosed() throws {
        XCTAssertThrowsError(try UpdateCatalog.latest(feed([item("9.0")], bundle: "another.app"), installedVersion: "1", installedBuild: "1"))
        for version in ["", "1..2", "-1", "latest", "1.beta"] {
            XCTAssertThrowsError(try UpdateCatalog.latest(feed([item(version)]), installedVersion: "1", installedBuild: "1"))
        }
    }
    func testOnlyThisRepositoryHTTPSReleaseIPAsAreAccepted() throws {
        for url in [
            "http://github.com/R347H4CK3R/Ghostline/releases/download/test/app.ipa",
            "https://github.com/other/repo/releases/download/test/app.ipa",
            "https://github.com.evil.example/R347H4CK3R/Ghostline/releases/download/test/app.ipa",
            "https://github.com/R347H4CK3R/Ghostline/releases/download/../app.ipa",
            "https://github.com/R347H4CK3R/Ghostline/releases/download/test/app.ipa?redirect=bad",
            "file:///tmp/app.ipa"
        ] {
            XCTAssertThrowsError(try UpdateCatalog.latest(feed([item("2", url: url)]), installedVersion: "1", installedBuild: "1"), url)
        }
    }
}
