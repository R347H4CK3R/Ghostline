import XCTest

@MainActor final class SpeechFeatureUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["-tutorialSeen", "YES"]; app.launch()
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 30)); return app
    }
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 { if element.exists && element.isHittable { return }; app.swipeUp() }
        XCTAssertTrue(element.waitForExistence(timeout: 10))
    }
    func testSpeechControlsCanBeChangedAndReset() {
        let app = launch()
        app.buttons["make-speech"].tap()
        let controls = app.buttons["Speech controls"]; reveal(controls, in: app); controls.tap()
        let speed = app.sliders["Speech speed"]; reveal(speed, in: app)
        speed.adjust(toNormalizedSliderPosition: 1)
        let pitch = app.sliders["Speech pitch"]; reveal(pitch, in: app)
        pitch.adjust(toNormalizedSliderPosition: 1)
        let reset = app.buttons["reset-speech-controls"]; reveal(reset, in: app); reset.tap()
        for _ in 0..<4 { if app.staticTexts["Speed · 1.00x"].isHittable { break }; app.swipeDown() }
        XCTAssertTrue(app.staticTexts["Speed · 1.00x"].exists)
        XCTAssertTrue(app.staticTexts["Pitch · +0 semitones"].exists)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.lifetime = .keepAlways; add(shot)
    }
    func testSuggestionRequiresPublicAcknowledgementAndRetainsDraft() {
        let app = launch(); app.tabBars.buttons["Settings"].tap()
        let link = app.buttons["Send a suggestion"]; reveal(link, in: app); link.tap()
        XCTAssertTrue(app.staticTexts["suggestion-public-warning"].waitForExistence(timeout: 10))
        let send = app.buttons["open-suggestion-draft"]
        reveal(send, in: app); XCTAssertFalse(send.isEnabled)
        let title = app.textFields["suggestion-title"]
        for _ in 0..<4 { if title.isHittable { break }; app.swipeDown() }
        title.tap(); title.typeText("Synthetic UI suggestion")
        let details = app.textViews["Suggestion details"]; details.tap(); details.typeText("Synthetic test draft, never submitted.")
        app.swipeUp()
        reveal(send, in: app); XCTAssertFalse(send.isEnabled)
        let acknowledge = app.switches["I understand that submitted text is public"]
        reveal(acknowledge, in: app); acknowledge.tap()
        XCTAssertTrue(send.isEnabled)
        // Do not open or submit an external issue from automated tests.
        app.terminate(); app.launch(); app.tabBars.buttons["Settings"].tap()
        let again = app.buttons["Send a suggestion"]; reveal(again, in: app); again.tap()
        let saved = app.textFields["suggestion-title"]; reveal(saved, in: app)
        XCTAssertEqual(saved.value as? String, "Synthetic UI suggestion")
        reveal(send, in: app); XCTAssertFalse(send.isEnabled, "Acknowledgement must not persist")
        let clear = app.buttons["Clear local draft"]; reveal(clear, in: app); clear.tap()
        XCTAssertFalse(send.isEnabled)
    }
}
