import XCTest
@MainActor final class LocalVideoStudioUITests: XCTestCase {
    func testStandaloneScreenCanReopenWithoutLaptopAndCannotGenerateWithoutMedia() {
        let app = XCUIApplication()
        app.launchArguments = ["-tutorialSeen", "YES", "-laptopURL", "https://127.0.0.1:9"]
        app.launch()
        for _ in 0..<2 {
            let open = app.buttons["local-video-studio"]
            XCTAssertTrue(open.waitForExistence(timeout: 25)); open.tap()
            XCTAssertTrue(app.navigationBars["Video Voice Studio"].waitForExistence(timeout: 15))
            let generate = app.buttons["local-video-generate"]
            for _ in 0..<5 where !generate.isHittable { app.swipeUp() }
            XCTAssertFalse(generate.isEnabled)
            XCTAssertTrue(app.buttons["local-video-import"].exists)
            let log = app.descendants(matching: .any)["local-video-live-log"].firstMatch
            for _ in 0..<8 where !log.isHittable { app.swipeUp() }
            XCTAssertTrue(log.exists)
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Standalone empty state and truthful live log"
            capture.lifetime = .keepAlways; add(capture)
            app.navigationBars["Video Voice Studio"].buttons.element(boundBy: 0).tap()
        }
    }
}
