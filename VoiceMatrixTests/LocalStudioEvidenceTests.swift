import XCTest
@testable import VoiceMatrix
final class LocalStudioEvidenceTests: XCTestCase {
    @MainActor func testNewCandidateCannotReusePreviousSpeakersPreview() {
        let now = Date()
        var job = LocalVideoStudio.Job(id: UUID(), created: now, updated: now,
                                      stage: "Testing", message: "Synthetic state")
        job.referenceFile = "reference-one.wav"
        job.previewFile = "preview-one.wav"
        XCTAssertEqual(job.matchingPreviewFile, "preview-one.wav")
        job.selectReference("reference-two.wav")
        XCTAssertNil(job.previewFile)
        XCTAssertNil(job.matchingPreviewFile)
        // Older saved jobs may already contain an inconsistent pair.
        job.previewFile = "preview-one.wav"
        XCTAssertNil(job.matchingPreviewFile)
        job.previewFile = "preview-two.wav"
        XCTAssertEqual(job.matchingPreviewFile, "preview-two.wav")
    }
    func testMissingFirstWordFailsTenPercentGate() {
        XCTAssertGreaterThan(LocalStudioEvidence.wordErrorRate(expected: "I found a strange device near the portal.", actual: "Found a strange device near the portal."), 0.1)
        XCTAssertEqual(LocalStudioEvidence.wordErrorRate(expected: "Hello, WORLD!", actual: "hello world"), 0)
    }
    func testTranscriptBoundsAndAnnotations() {
        XCTAssertFalse(LocalStudioEvidence.usableTranscript("♪ some music here"))
        XCTAssertFalse(LocalStudioEvidence.usableTranscript("[applause] then words"))
        XCTAssertFalse(LocalStudioEvidence.usableTranscript("hello"))
        XCTAssertTrue(LocalStudioEvidence.usableTranscript("Three ordinary spoken words."))
    }
    func testWindowsAreBoundedAndDoNotOverrunSource() {
        XCTAssertTrue(LocalStudioEvidence.windows(duration: .nan).isEmpty)
        XCTAssertTrue(LocalStudioEvidence.windows(duration: 1801).isEmpty)
        for duration in [3.0, 7.5, 17, 1800] {
            let rows = LocalStudioEvidence.windows(duration: duration)
            XCTAssertFalse(rows.isEmpty)
            XCTAssertLessThanOrEqual(rows.count, 300)
            XCTAssertTrue(rows.allSatisfy { $0.start >= 0 && $0.seconds >= 3 && $0.seconds <= 8 && $0.start + $0.seconds <= duration })
        }
    }
}
