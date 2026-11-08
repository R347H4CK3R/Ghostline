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
    func testStockLibraryIsEmptyAndSearchCannotRestoreRemovedVoices() {
        let app = launch(); app.tabBars.buttons["Voices"].tap()
        let notice = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Stock voices removed.")).firstMatch
        XCTAssertTrue(notice.waitForExistence(timeout: 10))
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10)); search.tap(); search.typeText("horror")
        XCTAssertTrue(notice.exists)
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "voice-")).count, 0)
    }
    func testMakeSpeechIsDisabledWithoutAUsableProfile() {
        let app = launch()
        let make = app.buttons["make-speech"]
        XCTAssertTrue(make.waitForExistence(timeout: 20)); make.tap()
        let speak = app.buttons["SPEAK"]
        XCTAssertTrue(speak.waitForExistence(timeout: 10)); XCTAssertFalse(speak.isEnabled)
        XCTAssertFalse(app.buttons["save-recording"].exists)
        app.tabBars.buttons["Home"].tap()
        XCTAssertTrue(app.staticTexts["MY CHARACTER FOLDER"].exists)
    }
}
