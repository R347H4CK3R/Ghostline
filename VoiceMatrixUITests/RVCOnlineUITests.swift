import XCTest

/// Navigation/unavailable-state checks only, not conversion or upload proof.
/// Closed loopback avoids the user's private laptop and all audio uploads.
@MainActor final class RVCOnlineUITests: XCTestCase {
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.waitForExistence(timeout: 10))
    }

    func testUnavailableLaptopNeverEnablesSendAcrossReopening() {
        let app = XCUIApplication()
        app.launchArguments = ["-tutorialSeen", "YES", "-laptopURL", "https://127.0.0.1:9"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 30))
        for _ in 0..<2 {
            let link = app.buttons["laptop-rvc"]
            reveal(link, in: app); link.tap()
            XCTAssertTrue(app.navigationBars["Laptop RVC"].waitForExistence(timeout: 15))
            XCTAssertTrue(app.staticTexts["ONLINE SPEECH-TO-SPEECH ONLY"].exists)
            let upload = app.buttons["rvc-send-audio"]
            reveal(upload, in: app)
            XCTAssertFalse(upload.isEnabled)
            XCTAssertTrue(app.staticTexts["rvc-job-stage"].exists)
            XCTAssertEqual(app.staticTexts["rvc-job-stage"].label, "Ready to prepare a request")
            XCTAssertFalse(app.buttons["rvc-cancel"].exists)
            let reconnect = app.buttons["rvc-reconnect"]
            reveal(reconnect, in: app)
            expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: reconnect)
            waitForExpectations(timeout: 25)
            reconnect.tap()
            XCTAssertFalse(upload.isEnabled)
            let screenshot = XCTAttachment(screenshot: app.screenshot())
            screenshot.name = "Online RVC unavailable with no uploaded request"
            screenshot.lifetime = .keepAlways; add(screenshot)
            app.navigationBars["Laptop RVC"].buttons.element(boundBy: 0).tap()
            XCTAssertTrue(app.tabBars.buttons["Home"].exists)
        }
    }
}
