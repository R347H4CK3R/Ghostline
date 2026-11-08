import XCTest

// UI-only checks: no model inference or generated-audio claim is made here.
@MainActor final class CharacterEmptyStateUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-tutorialSeen", "YES"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 30))
        return app
    }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<6 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.waitForExistence(timeout: 10))
    }

    private func capture(_ name: String, app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testEmptySpeechCannotGenerateOrClaimReview() {
        let app = launch()
        let make = app.buttons["make-speech"]
        XCTAssertTrue(make.waitForExistence(timeout: 20))
        reveal(make, in: app); make.tap()
        XCTAssertTrue(app.navigationBars["Make Speech"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["import-character-folder"].exists)
        let speak = app.buttons["Create Test Speech"]
        reveal(speak, in: app)
        XCTAssertFalse(speak.isEnabled, "An empty library must not synthesize a stock fallback")
        XCTAssertFalse(app.buttons["save-recording"].exists)
        XCTAssertFalse(app.buttons["character-match-yes"].exists)
        capture("Empty character speech is safely disabled", app: app)
    }

    func testEmptyConversionCannotRunWithoutRecordingOrCharacter() {
        let app = launch()
        let change = app.buttons["change-my-voice"]
        XCTAssertTrue(change.waitForExistence(timeout: 20))
        reveal(change, in: app); change.tap()
        XCTAssertTrue(app.navigationBars["Change My Voice"].waitForExistence(timeout: 20))
        let record = app.buttons["RECORD MY VOICE"]
        reveal(record, in: app)
        XCTAssertTrue(record.isEnabled)
        let convert = app.buttons["CONVERT"]
        reveal(convert, in: app)
        XCTAssertFalse(convert.isEnabled)
        XCTAssertFalse(app.buttons["save-recording"].exists)
        capture("Empty character conversion is safely disabled", app: app)
    }

    func testRepeatedFolderPickerCancellationAndTabNavigation() {
        let app = launch()
        app.tabBars.buttons["Voices"].tap()
        XCTAssertTrue(app.navigationBars["Make Speech"].waitForExistence(timeout: 20))
        let choose = app.buttons["import-character-folder"]
        for _ in 0..<2 {
            XCTAssertTrue(choose.waitForExistence(timeout: 20))
            reveal(choose, in: app); choose.tap()
            let cancel = app.buttons["Cancel"].firstMatch
            XCTAssertTrue(cancel.waitForExistence(timeout: 20))
            cancel.tap()
            XCTAssertTrue(choose.waitForExistence(timeout: 20))
            XCTAssertTrue(choose.isEnabled)
        }
        for tab in ["Saved", "Help", "Settings", "Home", "Voices"] {
            let button = app.tabBars.buttons[tab]
            XCTAssertTrue(button.waitForExistence(timeout: 15)); button.tap()
        }
        XCTAssertTrue(choose.waitForExistence(timeout: 20))
        capture("Character folder after repeated cancellation and navigation", app: app)
    }
}
