import XCTest

// Runs after empty-state tests. Imports a neutral synthetic collection through
// the real store; the availability-only build cannot perform neural synthesis.
@MainActor final class CharacterWorkflowUITests: XCTestCase {
    func testImportSelectListenAndKeepVoicesAfterRelaunch() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-tutorialSeen", "YES", "-ui-test-import"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Voices"].waitForExistence(timeout: 30))
        app.tabBars.buttons["Voices"].tap()
        let choose = app.buttons["choose-character"]
        XCTAssertTrue(choose.waitForExistence(timeout: 20))
        let ready = NSPredicate(format: "enabled == true")
        expectation(for: ready, evaluatedWith: choose)
        waitForExpectations(timeout: 30)
        choose.tap()
        XCTAssertTrue(app.navigationBars["Choose a voice"].waitForExistence(timeout: 15))
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 15))
        search.tap(); search.typeText("Synthetic")
        let voice = app.buttons["select-character-diagnostic-neutral"]
        XCTAssertTrue(voice.waitForExistence(timeout: 20))
        let details = app.buttons["Voice details"]
        XCTAssertTrue(details.exists)
        details.tap()
        XCTAssertTrue(voice.waitForExistence(timeout: 5), "Expanding details must keep the picker open")
        XCTAssertEqual(voice.value as? String, "Not selected")
        let sourceDetails = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Source: ")).firstMatch
        XCTAssertTrue(sourceDetails.waitForExistence(timeout: 5), "Voice details must expand")
        voice.tap()
        XCTAssertTrue(app.navigationBars["Make Speech"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["choose-character"].label.contains("Synthetic diagnostic voice"))
        let speak = app.buttons["create-character-speech"]
        reveal(speak, in: app)
        XCTAssertTrue(speak.isEnabled)
        let editor = app.textViews["Words for your character"]
        for _ in 0..<6 {
            if editor.exists && editor.isHittable &&
                editor.frame.minY > app.navigationBars.firstMatch.frame.maxY + 16 &&
                editor.frame.maxY < app.frame.maxY - 100 { break }
            app.swipeDown()
        }
        XCTAssertGreaterThan(editor.frame.minY, app.navigationBars.firstMatch.frame.maxY + 16)
        editor.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10))
        editor.typeText(String(repeating: "More words. ", count: 50))
        app.buttons["Done"].tap()
        XCTAssertGreaterThan((editor.value as? String ?? "").count, 500)
        reveal(speak, in: app); XCTAssertTrue(speak.isEnabled, "Long speech must not be disabled by the former character cap")
        let reference = app.buttons["1 · Listen to reference"]
        reveal(reference, in: app)
        reference.tap()
        let stop = app.buttons["stop-character-playback"]
        XCTAssertTrue(stop.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["character-playback-progress"].exists)
        stop.tap()
        XCTAssertTrue(stop.waitForNonExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["character-playback-error"].exists)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Imported voice and native reference playback"
        attachment.lifetime = .keepAlways
        add(attachment)
        app.terminate()
        app.launchArguments = ["-tutorialSeen", "YES"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Voices"].waitForExistence(timeout: 30))
        app.tabBars.buttons["Voices"].tap()
        XCTAssertTrue(choose.waitForExistence(timeout: 20))
        choose.tap()
        XCTAssertTrue(voice.waitForExistence(timeout: 30), "Imported references must survive an app restart")
        voice.tap()
        XCTAssertTrue(app.navigationBars["Make Speech"].waitForExistence(timeout: 15))
        reveal(reference, in: app)
        reference.tap()
        XCTAssertTrue(stop.waitForExistence(timeout: 10), "Reference must play from its private copy with the import source gone")
        stop.tap()
        XCTAssertTrue(stop.waitForNonExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["character-playback-error"].exists)
    }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists && element.isHittable)
    }
}
