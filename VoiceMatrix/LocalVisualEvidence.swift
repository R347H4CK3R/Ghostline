import Foundation
@preconcurrency import AVFoundation
import Vision
import ImageIO
import UniformTypeIdentifiers
import CryptoKit

/// Visible text and a sampled frame are evidence, not speaker identity.
/// No identity or speaking-character attribution is inferred from OCR or timing.
enum LocalVisualEvidence {
    struct Line: Codable, Sendable { let text: String; let confidence: Float }
    struct Frame: Codable, Sendable, Identifiable {
        let id: UUID
        let speaker: String
        let requestedSeconds: Double
        let actualSeconds: Double
        let file: String
        let sha256: String
        let lines: [Line]
    }
    struct Report: Codable, Sendable {
        let version: Int
        let sourceSHA256: String
        let audioOnly: Bool
        let requestedCount: Int
        let omittedSpeakers: Int
        let unavailableFrames: Int
        let frames: [Frame]
    }
    enum Failure: Error { case invalidSource, invalidEvidence, resourceBound }
    static func digest(_ data: Data) -> String { SHA256.hash(data:data).map { String(format:"%02x",$0) }.joined() }
    static func frameData(_ frame: Frame, folder: URL) throws -> Data {
        guard frame.file == "visual-" + frame.id.uuidString.lowercased() + ".jpg",
              frame.sha256.range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil,
              frame.speaker.range(of:"^[A-Za-z0-9_-]{1,40}$",options:.regularExpression) != nil,
              frame.requestedSeconds.isFinite, frame.actualSeconds.isFinite,
              (0...1800).contains(frame.requestedSeconds), (0...1800.05).contains(frame.actualSeconds),
              abs(frame.actualSeconds-frame.requestedSeconds) <= 0.15,
              frame.lines.count <= 8,
              frame.lines.allSatisfy({ !$0.text.isEmpty && $0.text.count <= 160 && $0.confidence.isFinite && (0...1).contains($0.confidence) }) else { throw Failure.invalidEvidence }
        let url = folder.appendingPathComponent(frame.file)
        let v = try url.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
        guard v.isRegularFile == true, v.isSymbolicLink != true, (1...250_000).contains(v.fileSize ?? 0) else { throw Failure.invalidEvidence }
        let data = try Data(contentsOf:url)
        guard digest(data) == frame.sha256,
              let image = CGImageSourceCreateWithData(data as CFData,nil), CGImageSourceGetCount(image) == 1,
              let properties = CGImageSourceCopyPropertiesAtIndex(image,0,nil) as? [CFString:Any],
              let w = properties[kCGImagePropertyPixelWidth] as? Int, let h = properties[kCGImagePropertyPixelHeight] as? Int,
              (1...640).contains(w), (1...640).contains(h) else { throw Failure.invalidEvidence }
        return data
    }
    static func frameURL(_ frame: Frame, folder: URL) throws -> URL {
        _ = try frameData(frame,folder:folder)
        return folder.appendingPathComponent(frame.file)
    }
    private static func sourceDigest(_ source: URL) throws -> String {
        let values=try source.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size=values.fileSize, (1...536_870_912).contains(size) else { throw Failure.invalidSource }
        let file=try FileHandle(forReadingFrom:source);defer { try? file.close() }
        var hash=SHA256(), count=0
        while let data=try file.read(upToCount:1_048_576), !data.isEmpty {
            try Task.checkCancellation();count += data.count
            guard count <= size else { throw Failure.invalidSource }
            hash.update(data:data)
        }
        try Task.checkCancellation()
        guard count == size else { throw Failure.invalidSource }
        return hash.finalize().map { String(format:"%02x",$0) }.joined()
    }
    static func validate(_ report: Report, sourceSHA256: String, folder: URL, groups: [LocalSpeakerPolicy.Speaker]) throws {
        guard report.version == 1, report.sourceSHA256 == sourceSHA256,
              (0...12).contains(report.requestedCount), (0...32).contains(report.omittedSpeakers),
              (0...report.requestedCount).contains(report.unavailableFrames),
              report.frames.count + report.unavailableFrames == report.requestedCount,
              !report.audioOnly || report.requestedCount == 0,
              Set(report.frames.map(\.id)).count == report.frames.count else { throw Failure.invalidEvidence }
        let selected = Array(groups.prefix(12))
        guard Set(report.frames.map(\.speaker)).count == report.frames.count,
              report.audioOnly || (report.requestedCount == selected.count && report.omittedSpeakers == groups.count-selected.count) else { throw Failure.invalidEvidence }
        for frame in report.frames {
            guard let group = selected.first(where: { $0.speaker == frame.speaker }), let window = group.windows.first,
                  abs(frame.requestedSeconds-(window.start+window.end)/2) < 0.000001 else { throw Failure.invalidEvidence }

            guard frame.speaker.range(of:"^[A-Za-z0-9_-]{1,40}$",options:.regularExpression) != nil,
                  frame.requestedSeconds.isFinite, frame.actualSeconds.isFinite,
                  frame.requestedSeconds >= 0, frame.actualSeconds >= 0,
                  abs(frame.actualSeconds-frame.requestedSeconds) <= 0.15,
                  frame.lines.count <= 8,
                  frame.lines.allSatisfy({ !$0.text.isEmpty && $0.text.count <= 160 && $0.confidence.isFinite && (0...1).contains($0.confidence) }) else { throw Failure.invalidEvidence }
            _ = try frameURL(frame,folder:folder)
        }
    }
    static func analyze(source: URL, sourceSHA256: String, groups: [LocalSpeakerPolicy.Speaker], folder: URL,
                        progress: @escaping @Sendable (Int,Int)->Void) async throws -> Report {
        guard source.isFileURL, sourceSHA256.range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil else { throw Failure.invalidSource }
        let v = try source.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
        let directory = try folder.resourceValues(forKeys:[.isDirectoryKey,.isSymbolicLinkKey])
        guard v.isRegularFile == true, v.isSymbolicLink != true, (1...536_870_912).contains(v.fileSize ?? 0),
              directory.isDirectory == true, directory.isSymbolicLink != true, groups.count <= 32 else { throw Failure.invalidSource }
        let worker = Task.detached(priority:.utility) {
            try Task.checkCancellation()
            guard try sourceDigest(source) == sourceSHA256 else { throw Failure.invalidSource }
            let asset = AVURLAsset(url:source)
            let tracks = try await asset.loadTracks(withMediaType:.video)
            guard !tracks.isEmpty else {
                guard try sourceDigest(source) == sourceSHA256 else { throw Failure.invalidSource }
                return Report(version:1,sourceSHA256:sourceSHA256,audioOnly:true,requestedCount:0,omittedSpeakers:0,unavailableFrames:0,frames:[])
            }
            guard tracks.count == 1 else { throw Failure.invalidSource }
            let duration = try await asset.load(.duration).seconds
            guard duration.isFinite, (0.1...1800).contains(duration) else { throw Failure.resourceBound }
            let selected = Array(groups.prefix(12))
            let generator = AVAssetImageGenerator(asset:asset)
            generator.appliesPreferredTrackTransform = true
            generator.maximumSize = CGSize(width:640,height:640)
            generator.requestedTimeToleranceBefore = CMTime(seconds:0.1,preferredTimescale:600)
            generator.requestedTimeToleranceAfter = CMTime(seconds:0.1,preferredTimescale:600)
            return try await withTaskCancellationHandler {
                var frames: [Frame] = [], unavailable = 0
                for (index,group) in selected.enumerated() {
                    try Task.checkCancellation()
                    guard group.speaker.range(of:"^[A-Za-z0-9_-]{1,40}$",options:.regularExpression) != nil,
                          let window = group.windows.first, window.start.isFinite, window.end.isFinite,
                          window.start >= 0, window.end > window.start, window.end <= duration + 0.05 else { throw Failure.invalidEvidence }
                    let seconds = (window.start + window.end)/2
                    do {
                        let result = try await generator.image(at:CMTime(seconds:seconds,preferredTimescale:600))
                        try Task.checkCancellation()
                        guard result.actualTime.seconds.isFinite, abs(result.actualTime.seconds-seconds) <= 0.15,
                              result.image.width <= 640, result.image.height <= 640 else { throw Failure.invalidEvidence }
                        let request = VNRecognizeTextRequest()
                        request.recognitionLevel = .accurate
                        request.usesLanguageCorrection = false
                        request.recognitionLanguages = ["en-US"]
                        let handler = VNImageRequestHandler(cgImage:result.image,options:[:])
                        try handler.perform([request])
                        try Task.checkCancellation()
                        let lines = (request.results ?? []).prefix(8).compactMap { observation -> Line? in
                            guard let candidate = observation.topCandidates(1).first, candidate.confidence.isFinite else { return nil }
                            let text = String(candidate.string.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }.map(String.init).joined().prefix(160))
                            guard !text.isEmpty else { return nil }
                            return Line(text:text,confidence:candidate.confidence)
                        }
                        let bytes = NSMutableData()
                        guard let encoder = CGImageDestinationCreateWithData(bytes,UTType.jpeg.identifier as CFString,1,nil) else { throw Failure.invalidEvidence }
                        CGImageDestinationAddImage(encoder,result.image,[kCGImageDestinationLossyCompressionQuality:0.7] as CFDictionary)
                        guard CGImageDestinationFinalize(encoder), (1...250_000).contains(bytes.length) else { throw Failure.resourceBound }
                        let id=UUID(), data=bytes as Data, filename="visual-"+id.uuidString.lowercased()+".jpg"
                        try Task.checkCancellation()
                        try data.write(to:folder.appendingPathComponent(filename),options:.withoutOverwriting)
                        frames.append(Frame(id:id,speaker:group.speaker,requestedSeconds:seconds,actualSeconds:result.actualTime.seconds,file:filename,sha256:digest(data),lines:lines))
                    } catch is CancellationError { throw CancellationError() }
                    catch { try Task.checkCancellation(); unavailable += 1 }
                    progress(index+1,selected.count)
                }
                guard try sourceDigest(source) == sourceSHA256 else { throw Failure.invalidSource }
                let report=Report(version:1,sourceSHA256:sourceSHA256,audioOnly:false,requestedCount:selected.count,omittedSpeakers:max(0,groups.count-selected.count),unavailableFrames:unavailable,frames:frames)
                try validate(report,sourceSHA256:sourceSHA256,folder:folder,groups:groups)
                return report
            } onCancel: { generator.cancelAllCGImageGeneration() }
        }
        return try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
    }
}
