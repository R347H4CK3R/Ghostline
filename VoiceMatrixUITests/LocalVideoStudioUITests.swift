import XCTest
import UIKit
@MainActor final class LocalVideoStudioUITests: XCTestCase {
    func testExplicitPasteStagesURLWithoutStartingDownloadAndRejectsOversize() {
        UIPasteboard.general.string = "https://youtu.be/AAAAAAAAAAA"
        let app = XCUIApplication()
        app.launchArguments = ["-tutorialSeen", "YES", "-laptopURL", "https://127.0.0.1:9"]
        app.launch()
        let open=app.buttons["local-video-studio"]
        XCTAssertTrue(open.waitForExistence(timeout:25));open.tap()
        let paste=app.buttons["local-video-paste"]
        XCTAssertTrue(paste.waitForExistence(timeout:15))
        for _ in 0..<4 where !paste.isHittable { app.swipeUp() }
        paste.tap()
        let field=app.textFields["local-video-url"]
        let staged=NSPredicate(format:"value == %@", "https://www.youtube.com/watch?v=AAAAAAAAAAA")
        expectation(for:staged,evaluatedWith:field)
        waitForExpectations(timeout:10)
        XCTAssertFalse(app.buttons["local-video-download"].isEnabled)
        UIPasteboard.general.string = String(repeating:"x",count:16_385)
        paste.tap()
        XCTAssertTrue(app.staticTexts["Clipboard must contain one supported video URL of at most 16,384 bytes."].waitForExistence(timeout:10))
        XCTAssertEqual(field.value as? String,"https://www.youtube.com/watch?v=AAAAAAAAAAA")
        XCTAssertFalse(app.buttons["local-video-download"].isEnabled)
    }

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
            XCTAssertTrue(app.buttons["local-video-paste"].exists)
            let log = app.descendants(matching: .any).matching(identifier: "local-video-live-log").firstMatch
            for _ in 0..<8 where !log.isHittable { app.swipeUp() }
            XCTAssertTrue(log.exists)
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Standalone empty state and truthful live log"
            capture.lifetime = .keepAlways; add(capture)
            app.navigationBars["Video Voice Studio"].buttons.element(boundBy: 0).tap()
        }
    }
}
