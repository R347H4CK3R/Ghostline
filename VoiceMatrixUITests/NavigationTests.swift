import XCTest
@MainActor final class NavigationTests: XCTestCase {
    private func launch() -> XCUIApplication {
        let app = XCUIApplication(); app.launchArguments = ["-tutorialSeen", "YES"]; app.launch(); return app
    }
    func testBeginnerNavigationAndEmptyRecordingCannotConvert() {
        let app = launch()
        let change = app.buttons["change-my-voice"]
        XCTAssertTrue(change.waitForExistence(timeout: 20)); change.tap()
        let convert = app.buttons["CONVERT"]
        XCTAssertTrue(convert.waitForExistence(timeout: 10)); XCTAssertFalse(convert.isEnabled)
        XCTAssertTrue(app.buttons["RECORD MY VOICE"].exists)
        for tab in ["Voices", "Saved", "Help", "Settings", "Home"] {
            XCTAssertTrue(app.tabBars.buttons[tab].exists); app.tabBars.buttons[tab].tap()
        }
    }
    func testGenreSearchAndSelectionAccessibility() {
        let app = launch(); app.tabBars.buttons["Voices"].tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10)); search.tap(); search.typeText("horror")
        let voice = app.buttons["voice-characters_Azgorath"]
        XCTAssertTrue(voice.waitForExistence(timeout: 10)); voice.tap()
        XCTAssertEqual(voice.value as? String, "Selected")
    }
    func testMakeSpeechProducesSaveableAudioInBeginnerFlow() {
        let app = launch()
        let make = app.buttons["make-speech"]
        XCTAssertTrue(make.waitForExistence(timeout: 20)); make.tap()
        let speak = app.buttons["SPEAK"]
        XCTAssertTrue(speak.waitForExistence(timeout: 10)); speak.tap()
        let save = app.buttons["save-recording"]
        XCTAssertTrue(save.waitForExistence(timeout: 90)); XCTAssertTrue(save.isEnabled); save.tap()
        XCTAssertEqual(save.label, "Saved"); XCTAssertFalse(save.isEnabled)
        app.tabBars.buttons["Saved"].tap()
        XCTAssertFalse(app.staticTexts["No recordings yet"].exists)
    }
}
