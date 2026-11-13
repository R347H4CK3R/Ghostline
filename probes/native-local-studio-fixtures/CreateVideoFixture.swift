import Foundation
import AVFoundation
import CoreGraphics
import CoreText

/// Original synthetic label plus installed neutral speech; no character or likeness claim.
@main struct CreateVideoFixture {
    enum Failure: Error { case arguments, invalidAudio, writer, deadline, mux }
    static func main() async throws {
        guard CommandLine.arguments.count == 3 else { throw Failure.arguments }
        let audioURL = URL(fileURLWithPath:CommandLine.arguments[1])
        let output = URL(fileURLWithPath:CommandLine.arguments[2])
        guard !FileManager.default.fileExists(atPath:output.path) else { throw Failure.arguments }
        let audio = AVURLAsset(url:audioURL)
        let duration = try await audio.load(.duration)
        let tracks = try await audio.loadTracks(withMediaType:.audio)
        guard (8...60).contains(duration.seconds),tracks.count == 1 else { throw Failure.invalidAudio }
        let silent = output.deletingLastPathComponent().appendingPathComponent("label-"+UUID().uuidString+".mov")
        let writer = try AVAssetWriter(outputURL:silent,fileType:.mov)
        let input = AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:640,AVVideoHeightKey:360])
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32ARGB,kCVPixelBufferWidthKey as String:640,kCVPixelBufferHeightKey as String:360])
        guard writer.canAdd(input) else { throw Failure.writer }
        writer.add(input)
        guard writer.startWriting() else { throw writer.error ?? Failure.writer }
        writer.startSession(atSourceTime:.zero)
        var optional:CVPixelBuffer?
        guard CVPixelBufferCreate(kCFAllocatorDefault,640,360,kCVPixelFormatType_32ARGB,nil,&optional)==kCVReturnSuccess,let buffer=optional else { throw Failure.writer }
        CVPixelBufferLockBaseAddress(buffer,[])
        guard let context=CGContext(data:CVPixelBufferGetBaseAddress(buffer),width:640,height:360,bitsPerComponent:8,bytesPerRow:CVPixelBufferGetBytesPerRow(buffer),space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipFirst.rawValue) else { throw Failure.writer }
        context.setFillColor(CGColor(gray:1,alpha:1));context.fill(CGRect(x:0,y:0,width:640,height:360))
        let text=NSAttributedString(string:"VISIBLE LABEL: DEMO",attributes:[NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Helvetica-Bold" as CFString,34,nil),NSAttributedString.Key(kCTForegroundColorAttributeName as String):CGColor(gray:0,alpha:1)])
        context.textPosition=CGPoint(x:45,y:170);CTLineDraw(CTLineCreateWithAttributedString(text),context)
        CVPixelBufferUnlockBaseAddress(buffer,[])
        for frame in 0..<Int(ceil(duration.seconds*12)) {
            let deadline=Date().addingTimeInterval(20)
            while !input.isReadyForMoreMediaData {
                guard writer.status == .writing,Date()<deadline else { throw writer.error ?? Failure.deadline }
                try await Task.sleep(nanoseconds:10_000_000)
            }
            guard adaptor.append(buffer,withPresentationTime:CMTime(value:Int64(frame),timescale:12)) else { throw writer.error ?? Failure.writer }
        }
        writer.endSession(atSourceTime:duration)
        input.markAsFinished();await writer.finishWriting()
        guard writer.status == .completed else { throw writer.error ?? Failure.writer }
        let video=AVURLAsset(url:silent)
        let videoTracks=try await video.loadTracks(withMediaType:.video)
        let composition=AVMutableComposition()
        guard videoTracks.count == 1,
              let vt=composition.addMutableTrack(withMediaType:.video,preferredTrackID:kCMPersistentTrackID_Invalid),
              let at=composition.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid) else { throw Failure.mux }
        let range=CMTimeRange(start:.zero,duration:duration)
        try vt.insertTimeRange(range,of:videoTracks[0],at:.zero)
        try at.insertTimeRange(range,of:tracks[0],at:.zero)
        guard let export=AVAssetExportSession(asset:composition,presetName:AVAssetExportPresetPassthrough) else { throw Failure.mux }
        try await export.export(to:output,as:.mov)
        let result=AVURLAsset(url:output)
        let resultAudio=try await result.loadTracks(withMediaType:.audio)
        let resultVideo=try await result.loadTracks(withMediaType:.video)
        let resultDuration=try await result.load(.duration)
        guard resultAudio.count == 1,resultVideo.count == 1,abs(resultDuration.seconds-duration.seconds)<0.1 else { throw Failure.mux }
        // Keep input and intermediate fixture for diagnostic reproducibility.
        print("Generated original neutral video with one audio and one label track; no identity claim.")
    }
}
