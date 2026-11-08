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
    func testVoicesTabOpensCharactersAndPickerCancellationKeepsScreenUsable() {
        let app = launch(); app.tabBars.buttons["Voices"].tap()
        let choose = app.buttons["import-character-folder"]
        XCTAssertTrue(choose.waitForExistence(timeout: 15))
        XCTAssertTrue(app.navigationBars["My Character Folder"].exists)
        XCTAssertTrue(app.otherElements["character-import-guide"].exists || app.staticTexts["Add your characters"].exists)
        choose.tap()
        let cancel = app.buttons["Cancel"].firstMatch
        XCTAssertTrue(cancel.waitForExistence(timeout: 10)); cancel.tap()
        XCTAssertTrue(choose.waitForExistence(timeout: 10)); XCTAssertTrue(choose.isEnabled)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "Empty character library with import steps"; shot.lifetime = .keepAlways; add(shot)
    }
    func testMakeSpeechOpensCharacterFolderWithoutStockFallback() {
        let app = launch()
        let make = app.buttons["make-speech"]
        XCTAssertTrue(make.waitForExistence(timeout: 20)); make.tap()
        XCTAssertTrue(app.buttons["import-character-folder"].waitForExistence(timeout: 10))
        let speak = app.buttons["Create Test Speech"]
        for _ in 0..<4 { if speak.exists { break }; app.swipeUp() }
        XCTAssertTrue(speak.waitForExistence(timeout: 10)); XCTAssertFalse(speak.isEnabled)
        XCTAssertFalse(app.buttons["save-recording"].exists)
        XCTAssertTrue(app.navigationBars["My Character Folder"].exists)
    }
}
