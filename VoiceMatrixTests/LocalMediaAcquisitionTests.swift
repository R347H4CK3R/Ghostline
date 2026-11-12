import XCTest
import AVFoundation
import CoreVideo
@testable import VoiceMatrix

final class LocalMediaAcquisitionTests: XCTestCase {
    func testRetentionScanCountsFilesAndRejectsMissingRootAndSymlinks() throws {
        let root=FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        XCTAssertThrowsError(try LocalMediaAcquisition.retainedBytes(root:root))
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false)
        defer { try? FileManager.default.removeItem(at:root) }
        XCTAssertEqual(try LocalMediaAcquisition.retainedBytes(root:root),0)
        let child=root.appendingPathComponent("job")
        try FileManager.default.createDirectory(at:child,withIntermediateDirectories:false)
        try Data(repeating:1,count:23).write(to:child.appendingPathComponent("source.wav"))
        try Data(repeating:2,count:7).write(to:root.appendingPathComponent("manifest.json"))
        XCTAssertEqual(try LocalMediaAcquisition.retainedBytes(root:root),30)
        try FileManager.default.createSymbolicLink(at:child.appendingPathComponent("alias"),withDestinationURL:root)
        XCTAssertThrowsError(try LocalMediaAcquisition.retainedBytes(root:root))
        XCTAssertThrowsError(try LocalMediaAcquisition.retainedBytes(root:child.appendingPathComponent("alias")))
    }
    func testArchiveRedirectPolicyAndSyntheticTransport() async throws {
        let origin=URL(string:"https://archive.org/download/example/source.mp4")!
        let node=URL(string:"https://ia800308.us.archive.org/21/items/example/source.mp4")!
        XCTAssertNoThrow(try LocalMediaURLPolicy.validateRedirect(from:origin,to:node,role:.direct))
        for target in ["https://ia800308.us.archive.org.evil.test/a.mp4","https://evil.archive.org/a.mp4","https://127.0.0.1/a.mp4","https://upload.wikimedia.org/a.mp4","http://ia800308.us.archive.org/a.mp4"] {
            XCTAssertThrowsError(try LocalMediaURLPolicy.validateRedirect(from:origin,to:URL(string:target)!,role:.direct))
        }
        let folder=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:folder) }
        let config=URLSessionConfiguration.ephemeral;config.protocolClasses=[SyntheticMediaProtocol.self]
        let result=try await LocalMediaAcquisition.Transfer.download(URL(string:"https://archive.org/redirect.mp4")!,role:.direct,folder:folder,ext:"mp4",maximumBytes:64,configuration:config) { _ in }
        XCTAssertEqual(result.bytes,32)
        do {
            _ = try await LocalMediaAcquisition.Transfer.download(URL(string:"https://archive.org/redirect-private.mp4")!,role:.direct,folder:folder,ext:"mp4",maximumBytes:64,configuration:config) { _ in }
            XCTFail("Private-network redirect accepted")
        } catch { }
    }
    func testStorageBudgetReservesOnlyFutureMergeAndAccountsForCompletedTracks() throws {
        XCTAssertEqual(try LocalMediaURLPolicy.byteBudget(retained:1_500_000_000,free:1_300_000_000,reserveForMerge:false),500_000_000)
        XCTAssertEqual(try LocalMediaURLPolicy.byteBudget(retained:1_000_000_000,free:1_800_000_000,reserveForMerge:true),500_000_000)
        XCTAssertEqual(try LocalMediaURLPolicy.byteBudget(retained:1_400_000_000,free:1_400_000_000,reserveForMerge:true,completedSourceBytes:400_000_000),100_000_000)
        XCTAssertEqual(try LocalMediaURLPolicy.byteBudget(retained:1_999_999_000,free:900_000_000,reserveForMerge:false),1_000)
        XCTAssertThrowsError(try LocalMediaURLPolicy.byteBudget(retained:2_000_000_000,free:2_000_000_000,reserveForMerge:false))
        XCTAssertThrowsError(try LocalMediaURLPolicy.byteBudget(retained:0,free:799_999_999,reserveForMerge:false))
    }
    func testAdaptiveMergeRunsOnSyntheticLocalTracksAndPreservesOriginals() async throws {
        let folder=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:folder) }
        let video=folder.appendingPathComponent("video.mp4"),pcm=folder.appendingPathComponent("tone.caf"),audio=folder.appendingPathComponent("audio.m4a")
        let writer=try AVAssetWriter(outputURL:video,fileType:.mp4)
        let input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:32,AVVideoHeightKey:32])
        let adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32ARGB,kCVPixelBufferWidthKey as String:32,kCVPixelBufferHeightKey as String:32])
        writer.add(input);XCTAssertTrue(writer.startWriting());writer.startSession(atSourceTime:.zero)
        var pixel:CVPixelBuffer?
        XCTAssertEqual(CVPixelBufferCreate(kCFAllocatorDefault,32,32,kCVPixelFormatType_32ARGB,nil,&pixel),kCVReturnSuccess)
        let buffer=try XCTUnwrap(pixel)
        CVPixelBufferLockBaseAddress(buffer,[])
        if let base=CVPixelBufferGetBaseAddress(buffer) { memset(base,0,CVPixelBufferGetBytesPerRow(buffer)*32) }
        CVPixelBufferUnlockBaseAddress(buffer,[])
        for frame in 0..<30 {
            var waits=0
            while !input.isReadyForMoreMediaData {
                try await Task.sleep(nanoseconds:10_000_000);waits += 1
                guard waits<500 else { throw LocalMediaURLPolicy.Failure.bounds }
            }
            XCTAssertTrue(adaptor.append(buffer,withPresentationTime:CMTime(value:Int64(frame),timescale:10)))
        }
        writer.endSession(atSourceTime:CMTime(seconds:3,preferredTimescale:600));input.markAsFinished()
        await withCheckedContinuation { (c:CheckedContinuation<Void,Never>) in writer.finishWriting { c.resume() } }
        XCTAssertEqual(writer.status,.completed)
        let format=try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate:16_000,channels:1))
        let samples=try XCTUnwrap(AVAudioPCMBuffer(pcmFormat:format,frameCapacity:48_000));samples.frameLength=48_000
        for i in 0..<48_000 { samples.floatChannelData![0][i]=Float(sin(Double(i)*2*Double.pi*220/16_000))*0.03 }
        do { let file=try AVAudioFile(forWriting:pcm,settings:format.settings);try file.write(from:samples) }
        let encode=try XCTUnwrap(AVAssetExportSession(asset:AVURLAsset(url:pcm),presetName:AVAssetExportPresetAppleM4A))
        try await encode.export(to:audio,as:.m4a)
        let originalVideo=try Data(contentsOf:video),originalAudio=try Data(contentsOf:audio)
        let merged=try await LocalMediaAcquisition.merge(video:video,audio:audio,folder:folder,maximumBytes:10_000_000) { _ in }
        try await LocalMediaAcquisition.verify(merged,folder:folder)
        let asset=AVURLAsset(url:folder.appendingPathComponent(merged.file))
        let videoTracks=try await asset.loadTracks(withMediaType:.video),audioTracks=try await asset.loadTracks(withMediaType:.audio)
        XCTAssertEqual(videoTracks.count,1);XCTAssertEqual(audioTracks.count,1)
        let duration=try await asset.load(.duration);XCTAssertEqual(duration.seconds,3,accuracy:0.1)
        XCTAssertEqual(try Data(contentsOf:video),originalVideo);XCTAssertEqual(try Data(contentsOf:audio),originalAudio)
    }
    func testDownloadWritesExactSyntheticBytesAndRetainsOversizePartial() async throws {
        let folder=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:folder) }
        let config=URLSessionConfiguration.ephemeral;config.protocolClasses=[SyntheticMediaProtocol.self]
        let url=URL(string:"https://upload.wikimedia.org/synthetic.wav")!
        do {
            _ = try await LocalMediaAcquisition.Transfer.download(url,role:.direct,folder:folder,ext:"../../escape",maximumBytes:64,configuration:config) { _ in }
            XCTFail("Unsafe destination extension accepted")
        } catch { }
        let result=try await LocalMediaAcquisition.Transfer.download(url,role:.direct,folder:folder,ext:"wav",maximumBytes:64,configuration:config) { _ in }
        XCTAssertEqual(try Data(contentsOf:folder.appendingPathComponent(result.file)),Data(repeating:42,count:32))
        try await LocalMediaAcquisition.verify(result,folder:folder)
        do {
            _ = try await LocalMediaAcquisition.Transfer.download(url,role:.direct,folder:folder,ext:"wav",maximumBytes:20,configuration:config) { _ in }
            XCTFail("Oversized response accepted")
        } catch { }
        let files=try FileManager.default.contentsOfDirectory(at:folder,includingPropertiesForKeys:nil)
        XCTAssertEqual(files.count,2,"Failed partial must not delete completed source or its own evidence")
        let partials=files.filter { $0.lastPathComponent != result.file }
        let partial=try Data(contentsOf:XCTUnwrap(partials.first))
        XCTAssertLessThanOrEqual(partial.count,20)
        XCTAssertTrue(partial.allSatisfy { $0 == 42 })
        try Data([1]).write(to:folder.appendingPathComponent(result.file))
        do { try await LocalMediaAcquisition.verify(result,folder:folder);XCTFail("Changed retained source accepted") } catch { }
    }
    func testCanceledDownloadNeverReportsSuccess() async throws {
        let folder=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:folder) }
        let config=URLSessionConfiguration.ephemeral;config.protocolClasses=[SyntheticMediaProtocol.self]
        let task=Task {
            try await LocalMediaAcquisition.Transfer.download(URL(string:"https://upload.wikimedia.org/wait.wav")!,role:.direct,folder:folder,ext:"wav",maximumBytes:64,configuration:config) { _ in }
        }
        try await Task.sleep(nanoseconds:100_000_000);task.cancel()
        do { _ = try await task.value;XCTFail("Canceled download succeeded") } catch is CancellationError { }
    }
    func testNormalizationAndHostBoundary() throws {
        XCTAssertEqual(try LocalMediaURLPolicy.input("https://youtu.be/abcdefghijk?t=4").absoluteString, "https://www.youtube.com/watch?v=abcdefghijk")
        for text in ["http://youtube.com/watch?v=abcdefghijk", "https://youtube.com.evil.test/watch?v=abcdefghijk", "https://user:password@youtube.com/watch?v=abcdefghijk", "https://127.0.0.1/a.mp4", "https://[::1]/a.mp4", "https://localhost/a.mp4", "https://www.youtube.com:444/watch?v=abcdefghijk", "https://youtube.com/watch?v=abcdefghijk&v=lmnopqrstuv"] {
            XCTAssertThrowsError(try LocalMediaURLPolicy.input(text), text)
        }
        XCTAssertNoThrow(try LocalMediaURLPolicy.input("https://upload.wikimedia.org/example.mp4"))
        XCTAssertThrowsError(try LocalMediaURLPolicy.validate(URL(string:"https://googlevideo.com.evil.test/file")!, role: .stream))
        XCTAssertThrowsError(try LocalMediaURLPolicy.validate(URL(string:"https://192.168.1.1/file")!, role: .stream))
    }
    private func page(status: String = "OK", stream: [String:Any], live: Bool = false) throws -> Data {
        let response: [String:Any] = ["playabilityStatus":["status":status], "videoDetails":["videoId":"abcdefghijk","isLiveContent":live,"lengthSeconds":"12"], "streamingData":["formats":[stream]]]
        let json = try JSONSerialization.data(withJSONObject:response)
        return Data(("<script>var ytInitialPlayerResponse = " + String(decoding:json,as:UTF8.self) + ";</script>").utf8)
    }
    private var progressive: [String:Any] { ["url":"https://rr1.googlevideo.com/videoplayback?token=private", "mimeType":"video/mp4; codecs=\"avc1.42001E, mp4a.40.2\"", "height":360, "contentLength":"100", "audioQuality":"AUDIO_QUALITY_MEDIUM"] }
    func testPublicDirectPlayerResponseAndRestrictions() throws {
        let plan = try LocalMediaURLPolicy.youtubePlan(page(), videoID:"abcdefghijk")
        XCTAssertEqual(plan.count,1)
        XCTAssertEqual(plan[0].kind,.combined)
    }
    private func page() throws -> Data { try page(stream: progressive) }
    func testNeverTreatRestrictedCipherOrHTMLAsSuccess() throws {
        XCTAssertThrowsError(try LocalMediaURLPolicy.youtubePlan(page(status:"LOGIN_REQUIRED",stream:progressive),videoID:"abcdefghijk"))
        XCTAssertThrowsError(try LocalMediaURLPolicy.youtubePlan(page(stream:progressive,live:true),videoID:"abcdefghijk"))
        var cipher=progressive; cipher.removeValue(forKey:"url");cipher["signatureCipher"]="secret"
        XCTAssertThrowsError(try LocalMediaURLPolicy.youtubePlan(page(stream:cipher),videoID:"abcdefghijk"))
        XCTAssertThrowsError(try LocalMediaURLPolicy.youtubePlan(Data("Sign in to confirm".utf8),videoID:"abcdefghijk"))
        XCTAssertThrowsError(try LocalMediaURLPolicy.youtubePlan(page(),videoID:"differentid"))
    }
    func testAdaptiveTracksSelectedWithoutAssumingProgressive() throws {
        var v=progressive;v["mimeType"]="video/mp4; codecs=\"avc1.42001E\"";v.removeValue(forKey:"audioQuality")
        let a:[String:Any] = ["url":"https://rr1.googlevideo.com/audio", "mimeType":"audio/mp4; codecs=\"mp4a.40.2\"", "contentLength":"100"]
        let response:[String:Any] = ["playabilityStatus":["status":"OK"],"videoDetails":["videoId":"abcdefghijk","isLiveContent":false,"lengthSeconds":"12"],"streamingData":["adaptiveFormats":[v,a]]]
        let json=try JSONSerialization.data(withJSONObject:response)
        let plan=try LocalMediaURLPolicy.youtubePlan(Data(("ytInitialPlayerResponse = " + String(decoding:json,as:UTF8.self)).utf8),videoID:"abcdefghijk")
        XCTAssertEqual(plan.map(\.kind),[.video,.audio])
    }
}

// Transport fixture has no sockets, private recordings or website dependencies.
private final class SyntheticMediaProtocol: URLProtocol {
    override class func canInit(with request:URLRequest)->Bool { request.url?.scheme == "https" }
    override class func canonicalRequest(for request:URLRequest)->URLRequest { request }
    override func startLoading() {
        guard let url=request.url else { return }
        if url.lastPathComponent == "redirect.mp4" || url.lastPathComponent == "redirect-private.mp4" {
            let target=URL(string:url.lastPathComponent == "redirect.mp4" ? "https://ia800308.us.archive.org/synthetic.mp4" : "https://127.0.0.1/synthetic.mp4")!
            let redirect=HTTPURLResponse(url:url,statusCode:302,httpVersion:"HTTP/1.1",headerFields:["Location":target.absoluteString])!
            client?.urlProtocol(self,wasRedirectedTo:URLRequest(url:target),redirectResponse:redirect)
            return
        }
        let response=HTTPURLResponse(url:url,statusCode:200,httpVersion:"HTTP/1.1",headerFields:["Content-Type":"audio/wav"])!
        client?.urlProtocol(self,didReceive:response,cacheStoragePolicy:.notAllowed)
        client?.urlProtocol(self,didLoad:Data(repeating:42,count:16))
        if url.lastPathComponent == "wait.wav" { return }
        client?.urlProtocol(self,didLoad:Data(repeating:42,count:16))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}
