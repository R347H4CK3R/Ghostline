import XCTest

// UI-only checks with test-only model-availability markers, never model weights.
// No inference or generated-audio claim is made here.
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
        XCTAssertFalse(app.staticTexts["The shared F5 engine is absent from this build. Your imported voice samples remain saved; speech testing becomes available in a build containing that engine."].exists)
        XCTAssertFalse(speak.isEnabled, "An empty library must not synthesize a stock fallback")
        let noOutput = app.staticTexts["Create speech with this character to listen or save."]
        reveal(noOutput, in: app)
        XCTAssertTrue(noOutput.exists)
        XCTAssertFalse(app.buttons["save-recording"].exists)
        let noReview = app.staticTexts["Create speech with the selected reference before reviewing it."]
        reveal(noReview, in: app)
        XCTAssertTrue(noReview.exists)
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
        XCTAssertFalse(app.staticTexts["This build needs the shared voice-changing engine before conversion can run."].exists)
        XCTAssertFalse(convert.isEnabled)
        let noReview = app.staticTexts["Create speech with the selected reference before reviewing it."]
        reveal(noReview, in: app)
        XCTAssertTrue(noReview.exists)
        XCTAssertFalse(app.buttons["save-recording"].exists)
        XCTAssertFalse(app.buttons["character-match-yes"].exists)
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
            XCTAssertTrue(cancel.waitForNonExistence(timeout: 20))
            XCTAssertTrue(choose.waitForExistence(timeout: 20))
            XCTAssertTrue(choose.isEnabled && choose.isHittable)
        }
        let conversionMode = app.segmentedControls.buttons["Change My Voice"]
        reveal(conversionMode, in: app); conversionMode.tap()
        let importAudio = app.buttons["Import Audio"]
        reveal(importAudio, in: app); importAudio.tap()
        let audioCancel = app.buttons["Cancel"].firstMatch
        XCTAssertTrue(audioCancel.waitForExistence(timeout: 20)); audioCancel.tap()
        XCTAssertTrue(audioCancel.waitForNonExistence(timeout: 20))
        XCTAssertTrue(app.navigationBars["Change My Voice"].waitForExistence(timeout: 20))
        for tab in ["Saved", "Help", "Settings", "Home", "Voices"] {
            let button = app.tabBars.buttons[tab]
            XCTAssertTrue(button.waitForExistence(timeout: 15)); button.tap()
            XCTAssertTrue(button.isSelected)
            if tab == "Home" { XCTAssertTrue(app.buttons["make-speech"].waitForExistence(timeout: 15)) }
            else if tab == "Voices" { XCTAssertTrue(app.navigationBars["Change My Voice"].waitForExistence(timeout: 15)) }
            else { XCTAssertTrue(app.navigationBars[tab == "Saved" ? "Saved Recordings" : tab].waitForExistence(timeout: 15)) }
        }
        for _ in 0..<6 {
            if choose.exists && choose.isHittable { break }
            app.swipeDown()
        }
        XCTAssertTrue(choose.waitForExistence(timeout: 20)); XCTAssertTrue(choose.isHittable)
        choose.tap()
        let folderCancel = app.buttons["Cancel"].firstMatch
        XCTAssertTrue(folderCancel.waitForExistence(timeout: 20)); folderCancel.tap()
        XCTAssertTrue(folderCancel.waitForNonExistence(timeout: 20))
        XCTAssertTrue(choose.isHittable)
        capture("Character folder after repeated cancellation and navigation", app: app)
    }
}
