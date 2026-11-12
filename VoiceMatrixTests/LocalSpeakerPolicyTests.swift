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
        XCTAssertEqual(result[0].windows.count, 3)
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
    func testDistinctTurnsPrecedeBoundedTailCropsAndInputOrderIsStable() throws {
        let one:[LocalSpeakerPolicy.Segment] = [.init(speaker:"S1",start:0,end:15)]
        let windows=try LocalSpeakerPolicy.speakerWindows(one,duration:15)[0].windows
        XCTAssertEqual(windows.count,3)
        for (window,seconds) in zip(windows,[8.0,4.0,3.0]) { XCTAssertEqual(window.seconds,seconds,accuracy:0.000001) }
        XCTAssertEqual(windows[1].end,14.85,accuracy:0.000001)
        let turns:[LocalSpeakerPolicy.Segment] = [.init(speaker:"S1",start:0,end:10),.init(speaker:"S1",start:12,end:20),.init(speaker:"S1",start:22,end:28)]
        let first=try LocalSpeakerPolicy.speakerWindows(turns,duration:28)
        let second=try LocalSpeakerPolicy.speakerWindows(Array(turns.reversed()),duration:28)
        XCTAssertEqual(first,second)
        XCTAssertEqual(first[0].windows.map(\.start),[0.15,12.15,22.15])
    }
    func testFallbacksNeverCrossExcludedOverlapAndNeverDuplicate() throws {
        let groups=try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:12),.init(speaker:"S2",start:5,end:16)],duration:16)
        for group in groups {
            XCTAssertLessThanOrEqual(group.windows.count,3)
            for (index,window) in group.windows.enumerated() {
                XCTAssertGreaterThanOrEqual(window.seconds,3)
                XCTAssertFalse(group.windows.prefix(index).contains(window))
                if group.speaker == "S1" { XCTAssertGreaterThanOrEqual(window.start,0.15);XCTAssertLessThanOrEqual(window.end,4.85) }
                else { XCTAssertGreaterThanOrEqual(window.start,12.15);XCTAssertLessThanOrEqual(window.end,15.85) }
            }
        }
    }
    func testTimelineStartBeyondDurationFailsClosed() {
        XCTAssertThrowsError(try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:10.01,end:10.04)],duration:10))
    }
    func testLegacyAnalysisUpgradesOnlyAfterExactLegacyValidation() throws {
        let segments:[LocalSpeakerPolicy.Segment] = [.init(speaker:"S1",start:0,end:15)]
        let legacyWindows=try LocalSpeakerPolicy.speakerWindows(segments,duration:15,includeFallbacks:false)
        let legacy=LocalSpeakerDiarization.Analysis(modelRevision:"df2625ac79a7ac6b65ad868fee6d80f320da4232",seconds:15,segments:segments,speakerWindows:legacyWindows)
        let bytes=try JSONEncoder().encode(legacy)
        let decoded=try JSONDecoder().decode(LocalSpeakerDiarization.Analysis.self,from:bytes)
        XCTAssertNil(decoded.selectionPolicyVersion)
        let upgraded=try LocalSpeakerDiarization.validatedForCurrentPolicy(decoded)
        XCTAssertEqual(upgraded.selectionPolicyVersion,2)
        XCTAssertEqual(upgraded.speakerWindows[0].windows.count,3)
        XCTAssertEqual(decoded.speakerWindows[0].windows.count,1)
        XCTAssertNoThrow(try LocalSpeakerDiarization.validate(upgraded))
        let tampered=LocalSpeakerDiarization.Analysis(modelRevision:legacy.modelRevision,seconds:15,segments:segments,speakerWindows:[.init(speaker:"S1",windows:[.init(start:2,end:10)])])
        XCTAssertThrowsError(try LocalSpeakerDiarization.validatedForCurrentPolicy(tampered))
        var unknown=legacy;unknown.selectionPolicyVersion=99
        XCTAssertThrowsError(try LocalSpeakerDiarization.validatedForCurrentPolicy(unknown))
    }
}
