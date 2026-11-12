import XCTest
@testable import VoiceMatrix
final class LocalSpeakerPolicyTests: XCTestCase {
    func testOverlapIsRemovedFromBothSpeakersNotAssignedToFirst() throws {
        let result = try LocalSpeakerPolicy.speakerWindows([
            .init(speaker: "S1", start: 0, end: 12), .init(speaker: "S2", start: 5, end: 16)
        ], duration: 16)
        XCTAssertEqual(result.map(\.speaker), ["S1", "S2"])
        XCTAssertEqual(result[0].windows[0].start, 0.15, accuracy: 0.001)
        XCTAssertLessThanOrEqual(result[0].windows[0].end, 4.85)
        XCTAssertGreaterThanOrEqual(result[1].windows[0].start, 12.15)
    }
    func testSameSpeakerDuplicatesDoNotCreateFalseOverlap() throws {
        let result = try LocalSpeakerPolicy.speakerWindows([
            .init(speaker: "S1", start: 0, end: 10), .init(speaker: "S1", start: 1, end: 9)
        ], duration: 10)
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(result[0].windows.count, 1)
        XCTAssertEqual(result[0].windows[0].end - result[0].windows[0].start, 8, accuracy: 0.001)
    }
    func testInvalidOrExcessiveInputFailsRatherThanInventingSpeakers() {
        XCTAssertThrowsError(try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:.nan,end:10)],duration:10))
        XCTAssertThrowsError(try LocalSpeakerPolicy.speakerWindows([.init(speaker:"../bad",start:0,end:10)],duration:10))
        XCTAssertThrowsError(try LocalSpeakerPolicy.speakerWindows((0..<33).map { .init(speaker:"S\($0)",start:Double($0),end:Double($0+4)) },duration:40))
    }
    func testShortOnlySpeakerRemainsVisibleWithoutUsableReference() throws {
        let result = try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:1)],duration:3)
        XCTAssertEqual(result.count,1)
        XCTAssertTrue(result[0].windows.isEmpty)
    }
}
