import Foundation
import AVFoundation
import CoreGraphics
import CoreText

@main struct Checks {
    static func movie(_ url:URL) async throws {
        let writer = try AVAssetWriter(outputURL:url,fileType:.mov)
        let input = AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:640,AVVideoHeightKey:360])
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32ARGB,kCVPixelBufferWidthKey as String:640,kCVPixelBufferHeightKey as String:360,kCVPixelBufferCGImageCompatibilityKey as String:true,kCVPixelBufferCGBitmapContextCompatibilityKey as String:true])
        precondition(writer.canAdd(input));writer.add(input)
        precondition(writer.startWriting());writer.startSession(atSourceTime:.zero)
        for second in 0...3 {
            let deadline=Date().addingTimeInterval(20)
            while !input.isReadyForMoreMediaData { precondition(Date()<deadline);try await Task.sleep(nanoseconds:10_000_000) }
            var optional:CVPixelBuffer?
            precondition(CVPixelBufferCreate(kCFAllocatorDefault,640,360,kCVPixelFormatType_32ARGB,nil,&optional)==kCVReturnSuccess)
            let buffer=optional!;CVPixelBufferLockBaseAddress(buffer,[])
            let context=CGContext(data:CVPixelBufferGetBaseAddress(buffer),width:640,height:360,bitsPerComponent:8,bytesPerRow:CVPixelBufferGetBytesPerRow(buffer),space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipFirst.rawValue)!
            context.setFillColor(CGColor(gray:1,alpha:1));context.fill(CGRect(x:0,y:0,width:640,height:360))
            let text=NSAttributedString(string:"VISIBLE LABEL: DEMO",attributes:[NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Helvetica-Bold" as CFString,34,nil),NSAttributedString.Key(kCTForegroundColorAttributeName as String):CGColor(gray:0,alpha:1)])
            context.textPosition=CGPoint(x:45,y:170);CTLineDraw(CTLineCreateWithAttributedString(text),context)
            CVPixelBufferUnlockBaseAddress(buffer,[])
            precondition(adaptor.append(buffer,withPresentationTime:CMTime(seconds:Double(second),preferredTimescale:600)))
        }
        input.markAsFinished();await writer.finishWriting();precondition(writer.status == .completed)
    }
    static func main() async throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("visual-native-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:root) }
        let source=root.appendingPathComponent("synthetic.mov");try await movie(source)
        let sourceBytes=try Data(contentsOf:source), hash=LocalVisualEvidence.digest(sourceBytes)
        let groups=[LocalSpeakerPolicy.Speaker(speaker:"00",windows:[.init(start:0.2,end:1.8)])]
        let beforeWrongHash=try FileManager.default.contentsOfDirectory(atPath:root.path)
        do { _=try await LocalVisualEvidence.analyze(source:source,sourceSHA256:String(repeating:"0",count:64),groups:groups,folder:root) { _,_ in };fatalError("Wrong supplied source hash accepted") } catch LocalVisualEvidence.Failure.sourceChanged {}
        let afterWrongHash=try FileManager.default.contentsOfDirectory(atPath:root.path)
        precondition(afterWrongHash == beforeWrongHash)
        let report=try await LocalVisualEvidence.analyze(source:source,sourceSHA256:hash,groups:groups,folder:root) { _,_ in }
        precondition(!report.audioOnly && report.frames.count == 1 && report.unavailableFrames == 0)
        let frame=report.frames[0]
        precondition(frame.speaker == "00" && abs(frame.actualSeconds-1)<0.15)
        precondition(frame.lines.contains { $0.text.uppercased().contains("DEMO") })
        let retainedBytes=try Data(contentsOf:source)
        precondition(retainedBytes == sourceBytes)
        try LocalVisualEvidence.validate(report,sourceSHA256:hash,folder:root,groups:groups)
        let copy=try JSONDecoder().decode(LocalVisualEvidence.Report.self,from:JSONEncoder().encode(report))
        try LocalVisualEvidence.validate(copy,sourceSHA256:hash,folder:root,groups:groups)
        do { try LocalVisualEvidence.validate(copy,sourceSHA256:String(repeating:"0",count:64),folder:root,groups:groups);fatalError("Wrong source accepted") } catch {}
        do { try LocalVisualEvidence.validate(copy,sourceSHA256:hash,folder:root,groups:[.init(speaker:"wrong",windows:[.init(start:0.2,end:1.8)])]);fatalError("Wrong speaker group accepted") } catch {}
        let badConfidence=LocalVisualEvidence.Frame(id:frame.id,speaker:frame.speaker,requestedSeconds:frame.requestedSeconds,actualSeconds:frame.actualSeconds,file:frame.file,sha256:frame.sha256,lines:[.init(text:"DEMO",confidence:1e20)])
        do { _=try LocalVisualEvidence.frameURL(badConfidence,folder:root);fatalError("Unsafe displayed confidence accepted") } catch {}
        let frameURL=try LocalVisualEvidence.frameURL(frame,folder:root)
        try Data("changed".utf8).write(to:frameURL)
        do { _=try LocalVisualEvidence.frameURL(frame,folder:root);fatalError("Changed frame accepted") } catch {}
        let malformed=LocalVisualEvidence.Frame(id:UUID(),speaker:"00",requestedSeconds:1,actualSeconds:1,file:"../source.mov",sha256:hash,lines:[])
        do { _=try LocalVisualEvidence.frameURL(malformed,folder:root);fatalError("Path traversal accepted") } catch {}
        do {
            _=try await LocalVisualEvidence.analyze(source:source,sourceSHA256:hash,groups:groups,folder:root) { _,_ in
                try? Data("changed during extraction".utf8).write(to:source)
            }
            fatalError("Changed source accepted")
        } catch LocalVisualEvidence.Failure.sourceChanged {}
        let changedBytes=try Data(contentsOf:source)
        precondition(changedBytes == Data("changed during extraction".utf8))
        try sourceBytes.write(to:source)
        let audio=root.appendingPathComponent("audio.wav")
        do {
            let format=AVAudioFormat(standardFormatWithSampleRate:16_000,channels:1)!
            let buffer=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:16_000)!;buffer.frameLength=16_000
            for i in 0..<16_000 { buffer.floatChannelData![0][i]=0 }
            let file=try AVAudioFile(forWriting:audio,settings:format.settings);try file.write(from:buffer)
        }
        let audioHash=LocalVisualEvidence.digest(try Data(contentsOf:audio))
        let audioOnly=try await LocalVisualEvidence.analyze(source:audio,sourceSHA256:audioHash,groups:groups,folder:root) { _,_ in }
        precondition(audioOnly.audioOnly && audioOnly.frames.isEmpty)
        let cancelled=Task { try await LocalVisualEvidence.analyze(source:source,sourceSHA256:hash,groups:groups,folder:root) { _,_ in } }
        cancelled.cancel()
        do { _=try await cancelled.value;fatalError("Cancelled scan succeeded") } catch is CancellationError {}
        print("PASS actual AVFoundation video frame extraction and Vision OCR; source retention; audio-only behavior; report reload; source/hash/path rejection; cancellation. No identity or likeness claim.")
    }
}
