import Foundation
import AVFoundation
import CoreMedia
import CryptoKit
@preconcurrency import SoundAnalysis

/// Uses the OS classifier on a bounded retained candidate, without a service fallback.
enum LocalSoundQuality {
    struct Evidence: Codable, Sendable {
        let schemaVersion: Int
        let policyVersion: Int
        let classifier: String
        let osVersion: String
        let requiredLabels: [String]
        let sourceSHA256: String
        let seconds: Double
        let frames: [LocalSoundQualityPolicy.Frame]
        let decision: LocalSoundQualityPolicy.Decision
    }
    enum Failure: LocalizedError {
        case invalidSource, unavailableLabels, incompleteEvidence, analysisFailed, deadline
        var errorDescription:String? {
            switch self {
            case .invalidSource: return "Sound screening needs a retained mono WAV lasting 1–15 seconds and no larger than 1.5 MB. The candidate was kept."
            case .unavailableLabels: return "This iPhone's built-in sound classifier does not expose the required speech, music and singing labels. Generation stopped without bypassing screening."
            case .incompleteEvidence: return "The built-in sound classifier returned incomplete or invalid evidence. The candidate was retained, not marked clean."
            case .analysisFailed: return "On-device sound screening could not finish. The candidate was retained; no server fallback was used."
            case .deadline: return "On-device sound screening exceeded 30 seconds and cancellation was requested. The candidate was retained for retry."
            }
        }
    }
    static func analyze(source:URL, progress:@escaping @Sendable (String)->Void) async throws -> Evidence {
        try Task.checkCancellation()
        let session=Session(progress:progress)
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { session.start(source:source,continuation:$0) }
        } onCancel: { session.cancel() }
    }
    /// All mutable state is confined to `queue`; callbacks carry only value snapshots.
    private final class Session: NSObject, SNResultsObserving, @unchecked Sendable {
        private let queue=DispatchQueue(label:"com.voicematrix.local-sound-quality",qos:.userInitiated)
        private let progress:@Sendable (String)->Void
        private var analyzer:SNAudioFileAnalyzer?
        private var soundRequest:SNClassifySoundRequest?
        private var continuation:CheckedContinuation<Evidence,Error>?
        private var pending:Result<Evidence,Error>?
        private var finished=false
        private var timeout:DispatchWorkItem?
        private var duration=0.0
        private var sourceHash=""
        private var frames:[LocalSoundQualityPolicy.Frame]=[]
        private let labels=["speech","music","singing"]
        init(progress:@escaping @Sendable (String)->Void) { self.progress=progress }
        func start(source:URL,continuation:CheckedContinuation<Evidence,Error>) {
            queue.async {
                self.continuation=continuation
                if let pending=self.pending { self.finish(pending);return }
                do {
                    let bytes=try Self.checkedBytes(source)
                    let file=try AVAudioFile(forReading:source)
                    let seconds=Double(file.length)/file.fileFormat.sampleRate
                    guard file.fileFormat.channelCount==1,seconds.isFinite,(1...15).contains(seconds) else { throw Failure.invalidSource }
                    self.duration=seconds
                    self.sourceHash=SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined()
                    let request=try SNClassifySoundRequest(classifierIdentifier: .version1)
                    let known=Set(request.knownClassifications)
                    guard self.labels.allSatisfy(known.contains) else { throw Failure.unavailableLabels }
                    // Apple's version1 supports 0.5–15-second windows; one second
                    // resolves brief contamination without score normalization.
                    request.windowDuration=CMTime(seconds:1,preferredTimescale:48_000)
                    request.overlapFactor=0.5
                    let analyzer=try SNAudioFileAnalyzer(url:source)
                    self.analyzer=analyzer;self.soundRequest=request
                    try analyzer.add(request,withObserver:self)
                    let deadline=DispatchWorkItem { [weak self] in self?.finish(.failure(Failure.deadline)) }
                    self.timeout=deadline
                    self.queue.asyncAfter(deadline:.now() + .seconds(30),execute:deadline)
                    self.progress("Checking the candidate locally for speech, music and singing evidence.")
                    analyzer.analyze { [weak self] success in
                        guard let self else { return }
                        self.queue.async {
                            guard !self.finished else { return }
                            guard success else { self.finish(.failure(Failure.analysisFailed));return }
                            guard !self.frames.isEmpty else { self.finish(.failure(Failure.incompleteEvidence));return }
                            do {
                                let after=try Self.checkedBytes(source)
                                guard SHA256.hash(data:after).map({String(format:"%02x",$0)}).joined()==self.sourceHash else { throw Failure.invalidSource }
                            } catch { self.finish(.failure(Failure.invalidSource));return }
                            let result=Evidence(schemaVersion:1,policyVersion:LocalSoundQualityPolicy.version,classifier:"Apple SoundAnalysis.version1",osVersion:ProcessInfo.processInfo.operatingSystemVersionString,requiredLabels:self.labels,sourceSHA256:self.sourceHash,seconds:self.duration,frames:self.frames,decision:LocalSoundQualityPolicy.evaluate(self.frames,duration:self.duration))
                            self.finish(.success(result))
                        }
                    }
                } catch let failure as Failure { self.finish(.failure(failure)) }
                catch { self.finish(.failure(Failure.analysisFailed)) }
            }
        }
        private static func checkedBytes(_ source:URL) throws -> Data {
            guard source.isFileURL,source.pathExtension.lowercased()=="wav" else { throw Failure.invalidSource }
            let v=try source.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
            guard v.isRegularFile==true,v.isSymbolicLink != true,let size=v.fileSize,(1...1_500_000).contains(size) else { throw Failure.invalidSource }
            let handle=try FileHandle(forReadingFrom:source);defer { try? handle.close() }
            let bytes=try handle.read(upToCount:1_500_001) ?? Data()
            guard bytes.count==size else { throw Failure.invalidSource }
            return bytes
        }
        func cancel() { queue.async { self.finish(.failure(CancellationError())) } }
        private func finish(_ result:Result<Evidence,Error>) {
            guard !finished else { return }
            guard let continuation else { pending=result;return }
            finished=true;self.continuation=nil;pending=nil
            timeout?.cancel();timeout=nil
            analyzer?.cancelAnalysis();analyzer=nil;soundRequest=nil
            continuation.resume(with:result)
        }
        func request(_ request:SNRequest,didProduce result:SNResult) {
            guard let value=result as? SNClassificationResult,
                  let speech=value.classification(forIdentifier:"speech"),
                  let music=value.classification(forIdentifier:"music"),
                  let singing=value.classification(forIdentifier:"singing") else {
                queue.async { self.finish(.failure(Failure.incompleteEvidence)) };return
            }
            let frame=LocalSoundQualityPolicy.Frame(start:value.timeRange.start.seconds,end:CMTimeRangeGetEnd(value.timeRange).seconds,speech:speech.confidence,music:music.confidence,singing:singing.confidence)
            queue.async {
                guard !self.finished else { return }
                guard self.frames.count < 128,[frame.start,frame.end,frame.speech,frame.music,frame.singing].allSatisfy(\.isFinite) else { self.finish(.failure(Failure.incompleteEvidence));return }
                self.frames.append(frame)
                self.progress("Sound screening produced \(self.frames.count) local analysis windows.")
            }
        }
        func request(_ request:SNRequest,didFailWithError error:Error) { queue.async { self.finish(.failure(Failure.analysisFailed)) } }
        func requestDidComplete(_ request:SNRequest) { /* File completion closes the evidence. */ }
    }
}
