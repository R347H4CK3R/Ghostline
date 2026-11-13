import XCTest
@testable import VoiceMatrix
final class LocalStudioEvidenceTests: XCTestCase {
    @MainActor func testIndividualSpeakerAssetsSurviveReloadAndRejectChangedBytes() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let now=Date(), id=UUID(), first=Data(repeating:1,count:44), second=Data(repeating:2,count:44)
        let folder=root.appendingPathComponent(id.uuidString.lowercased())
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        var job=LocalVideoStudio.Job(id:id,created:now,updated:now,stage:"Testing",message:"Synthetic receipt integrity only")
        job.speakerVoiceIDs=["one":"voice-one","two":"voice-two"]
        job.speakerAssets=[:]
        for (speaker,bytes) in [("one",first),("two",second)] {
            let hash=LocalVisualEvidence.digest(bytes)
            job.speakerAssets?[speaker]=LocalVideoStudio.SpeakerAssets(voiceID:"voice-"+speaker,referenceFile:"reference-"+speaker+".wav",referenceSHA256:hash,previewFile:"preview-"+speaker+".wav",previewSHA256:hash)
            try bytes.write(to:folder.appendingPathComponent("reference-"+speaker+".wav"))
            try bytes.write(to:folder.appendingPathComponent("preview-"+speaker+".wav"))
        }
        try JSONEncoder().encode(job).write(to:folder.appendingPathComponent("job.json"))
        let studio=LocalVideoStudio(root:root,asrBundle:nil,f5Bundle:nil,speakerBundle:nil)
        XCTAssertEqual(studio.speakerAssetURL("one",preview:false)?.lastPathComponent,"reference-one.wav")
        XCTAssertEqual(studio.speakerAssetURL("two",preview:true)?.lastPathComponent,"preview-two.wav")
        XCTAssertNil(studio.speakerAssetURL("absent",preview:true))
        try first.write(to:folder.appendingPathComponent("preview-two.wav"))
        XCTAssertNil(studio.speakerAssetURL("two",preview:true))
        XCTAssertNotNil(studio.speakerAssetURL("one",preview:true))
        // Pair must be intact even if only its unchanged reference was requested.
        XCTAssertNil(studio.speakerAssetURL("two",preview:false))
        XCTAssertTrue(FileManager.default.fileExists(atPath:folder.appendingPathComponent("preview-two.wav").path))
        job.speakerAssets?["one"]=LocalVideoStudio.SpeakerAssets(voiceID:"voice-one",referenceFile:"reference-one.wav",referenceSHA256:LocalVisualEvidence.digest(first),previewFile:"preview-two.wav",previewSHA256:LocalVisualEvidence.digest(first))
        try JSONEncoder().encode(job).write(to:folder.appendingPathComponent("job.json"))
        let reopened=LocalVideoStudio(root:root,asrBundle:nil,f5Bundle:nil,speakerBundle:nil)
        XCTAssertNil(reopened.speakerAssetURL("one",preview:true))
        job.speakerAssets?["one"]=LocalVideoStudio.SpeakerAssets(voiceID:"wrong-voice",referenceFile:"reference-one.wav",referenceSHA256:LocalVisualEvidence.digest(first),previewFile:"preview-one.wav",previewSHA256:LocalVisualEvidence.digest(first))
        try JSONEncoder().encode(job).write(to:folder.appendingPathComponent("job.json"))
        XCTAssertNil(LocalVideoStudio(root:root,asrBundle:nil,f5Bundle:nil,speakerBundle:nil).speakerAssetURL("one",preview:true))
        job.speakerAssets=nil // Older job versions must remain readable without inventing a pair.
        try JSONEncoder().encode(job).write(to:folder.appendingPathComponent("job.json"))
        let legacy=LocalVideoStudio(root:root,asrBundle:nil,f5Bundle:nil,speakerBundle:nil)
        XCTAssertEqual(legacy.current?.id,id)
        XCTAssertNil(legacy.speakerAssetURL("one",preview:false))
    }
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
    @MainActor func testSimilarityCannotFollowChangedReferenceOrInvalidMetric() {
        let now=Date(), hash=String(repeating:"a",count:64)
        var job=LocalVideoStudio.Job(id:UUID(),created:now,updated:now,stage:"Testing",message:"Synthetic state")
        job.referenceFile="reference-one.wav";job.previewFile="preview-one.wav"
        let report=SpeakerSimilarityService.Report(schemaVersion:1,referenceSHA256:hash,generatedSHA256:hash,modelRevision:SpeakerSimilarityService.modelRevision,algorithm:"bundled-raw256-l2-cosine-v1",referenceSeconds:4,generatedSeconds:4,cosineSimilarity:0.4)
        job.similarity=LocalVideoStudio.Similarity(referenceFile:"reference-one.wav",previewFile:"preview-one.wav",measured:now,report:report)
        XCTAssertNotNil(job.matchingSimilarity)
        job.selectReference("reference-two.wav")
        XCTAssertNil(job.similarity);XCTAssertNil(job.matchingSimilarity)
        job.previewFile="preview-two.wav"
        job.similarity=LocalVideoStudio.Similarity(referenceFile:"reference-one.wav",previewFile:"preview-one.wav",measured:now,report:report)
        XCTAssertNil(job.matchingSimilarity)
        let invalid=SpeakerSimilarityService.Report(schemaVersion:1,referenceSHA256:hash,generatedSHA256:hash,modelRevision:SpeakerSimilarityService.modelRevision,algorithm:"bundled-raw256-l2-cosine-v1",referenceSeconds:4,generatedSeconds:4,cosineSimilarity:.nan)
        job.similarity=LocalVideoStudio.Similarity(referenceFile:"reference-two.wav",previewFile:"preview-two.wav",measured:now,report:invalid)
        XCTAssertNil(job.matchingSimilarity)
    }
    @MainActor func testReloadedSimilarityIsWithheldWhenRetainedBytesChange() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let now=Date(), id=UUID(), bytes=Data(repeating:1,count:44)
        let folder=root.appendingPathComponent(id.uuidString.lowercased())
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        let hash=LocalVisualEvidence.digest(bytes)
        var job=LocalVideoStudio.Job(id:id,created:now,updated:now,stage:"Testing",message:"Hash-binding test only")
        job.referenceFile="reference-one.wav";job.previewFile="preview-one.wav"
        let report=SpeakerSimilarityService.Report(schemaVersion:1,referenceSHA256:hash,generatedSHA256:hash,modelRevision:SpeakerSimilarityService.modelRevision,algorithm:"bundled-raw256-l2-cosine-v1",referenceSeconds:4,generatedSeconds:4,cosineSimilarity:0.4)
        job.similarity=LocalVideoStudio.Similarity(referenceFile:"reference-one.wav",previewFile:"preview-one.wav",measured:now,report:report)
        try bytes.write(to:folder.appendingPathComponent("reference-one.wav"))
        try bytes.write(to:folder.appendingPathComponent("preview-one.wav"))
        try JSONEncoder().encode(job).write(to:folder.appendingPathComponent("job.json"))
        let studio=LocalVideoStudio(root:root,asrBundle:nil,f5Bundle:nil,speakerBundle:nil)
        XCTAssertNotNil(studio.validatedSimilarity())
        try Data(repeating:2,count:44).write(to:folder.appendingPathComponent("preview-one.wav"))
        XCTAssertNil(studio.validatedSimilarity())
        let reopened=LocalVideoStudio(root:root,asrBundle:nil,f5Bundle:nil,speakerBundle:nil)
        XCTAssertNil(reopened.validatedSimilarity())
        XCTAssertTrue(FileManager.default.fileExists(atPath:folder.appendingPathComponent("preview-one.wav").path))
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
