import Foundation
import AVFoundation
import CoreMedia
import CryptoKit
@preconcurrency import CoreML
import FluidAudio

/// Local model bytes are verified before loading. No downloads, purge or service fallback.
enum LocalSpeakerDiarization {
    struct Analysis: Codable, Sendable {
        let modelRevision: String
        let seconds: Double
        let segments: [LocalSpeakerPolicy.Segment]
        let speakerWindows: [LocalSpeakerPolicy.Speaker]
    }
    enum Failure: LocalizedError {
        case bundleUnavailable, invalidBundle, invalidAudio, invalidTimeline, resourceBound
        var errorDescription: String? {
            switch self {
            case .bundleUnavailable: return "Bundled speaker analysis is missing. Install a complete standalone build. No laptop or server fallback was used."
            case .invalidBundle: return "Bundled speaker analysis failed its integrity check. Existing voices and media were retained."
            case .invalidAudio: return "Speaker analysis needs one readable audio track in local media. No speakers were invented."
            case .invalidTimeline: return "The audio timeline has a gap or offset over 50 milliseconds, which could select the wrong speaker. Export the media with a continuous audio track and import it again. Your original and existing voices were retained."
            case .resourceBound: return "Speaker analysis exceeded this app's safety limit. Retained media and voices are unchanged."
            }
        }
    }
    private struct Lock: Decodable { struct File: Decodable { let size:Int; let sha256:String }; let revision:String; let files:[String:File] }
    private static let revision = "df2625ac79a7ac6b65ad868fee6d80f320da4232"
    static func validate(_ analysis: Analysis) throws {
        guard analysis.modelRevision == revision else { throw Failure.invalidBundle }
        let expected = try LocalSpeakerPolicy.speakerWindows(analysis.segments,duration:analysis.seconds)
        guard expected == analysis.speakerWindows else { throw Failure.invalidAudio }
    }
    static func analyze(source: URL, bundle: URL? = Bundle.main.url(forResource:"Diarization",withExtension:nil), progress: @escaping @Sendable (String) -> Void) async throws -> Analysis {
        guard let bundle else { throw Failure.bundleUnavailable }
        let worker = Task.detached(priority:.userInitiated) {
            try Task.checkCancellation()
            progress("Checking bundled speaker-analysis hashes.")
            try verify(bundle)
            progress("Decoding local audio for speaker analysis.")
            let samples = try await decode(source,progress:progress)
            try Task.checkCancellation()
            progress("Loading bundled speaker-analysis models. No network is used.")
            let start = Date()
            func model(_ name: String, cpuOnly: Bool = false) throws -> MLModel {
                try Task.checkCancellation()
                let config = MLModelConfiguration(); config.computeUnits = cpuOnly ? .cpuOnly : .all
                return try MLModel(contentsOf:bundle.appendingPathComponent(name+".mlmodelc"),configuration:config)
            }
            let psiData = try Data(contentsOf:bundle.appendingPathComponent("plda-parameters.json"))
            guard let object = try JSONSerialization.jsonObject(with:psiData) as? [String:Any],
                  let tensors = object["tensors"] as? [String:Any], let psi = tensors["psi"] as? [String:Any],
                  let base64 = psi["data_base64"] as? String, let bytes = Data(base64Encoded:base64), bytes.count == 128*4 else { throw Failure.invalidBundle }
            let values: [Double] = bytes.withUnsafeBytes { raw in (0..<128).map { Double(Float(bitPattern:UInt32(littleEndian:raw.loadUnaligned(fromByteOffset:$0*4,as:UInt32.self)))) } }
            guard values.allSatisfy({ $0.isFinite && $0 >= 0 }) else { throw Failure.invalidBundle }
            let models = try OfflineDiarizerModels(segmentationModel:model("Segmentation"),fbankModel:model("FBank",cpuOnly:true),embeddingModel:model("Embedding"),pldaRhoModel:model("PldaRho"),pldaPsi:values,compilationDuration:Date().timeIntervalSince(start))
            var config = OfflineDiarizerConfig()
            config.segmentation.batchSize = 1
            config.embedding.batchSize = 1
            config.embedding.excludeOverlap = true
            config.postProcessing.exclusiveSegments = false
            config.exposeChunkEmbeddings = false
            let manager = OfflineDiarizerManager(config:config)
            manager.initialize(models:models)
            try Task.checkCancellation()
            progress("Analyzing speaker turns locally; model activity updates follow completed chunks.")
            let result = try await manager.process(audio:samples) { done,total in progress("Speaker analysis processed \(done) of \(total) chunks.") }
            try Task.checkCancellation()
            let duration = Double(samples.count)/16_000
            let segments = result.segments.map { LocalSpeakerPolicy.Segment(speaker:$0.speakerId,start:Double($0.startTimeSeconds),end:Double($0.endTimeSeconds)) }
            let windows = try LocalSpeakerPolicy.speakerWindows(segments,duration:duration)
            return Analysis(modelRevision:revision,seconds:duration,segments:segments,speakerWindows:windows)
        }
        return try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
    }
    private static func verify(_ root: URL) throws {
        let lockURL = root.appendingPathComponent("resource-lock.json")
        guard let data = try? Data(contentsOf:lockURL), data.count <= 65_536,
              SHA256.hash(data:data).map({String(format:"%02x",$0)}).joined() == "137ad0aba1483d0ba3c74cb5380ab05f5cd76a5eb47aa69b9de41c353315e7e0",
              let lock = try? JSONDecoder().decode(Lock.self,from:data), lock.revision == revision, (21...40).contains(lock.files.count) else { throw Failure.invalidBundle }
        for (name,entry) in lock.files {
            try Task.checkCancellation()
            let parts = name.split(separator:"/",omittingEmptySubsequences:false)
            guard !parts.isEmpty, !name.contains("\\"), parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }), entry.size > 0, entry.size <= 25_000_000 else { throw Failure.invalidBundle }
            var path = root
            for part in parts { path.appendPathComponent(String(part)); let v = try path.resourceValues(forKeys:[.isSymbolicLinkKey]); guard v.isSymbolicLink != true else { throw Failure.invalidBundle } }
            let v = try path.resourceValues(forKeys:[.isRegularFileKey,.fileSizeKey])
            guard v.isRegularFile == true, v.fileSize == entry.size else { throw Failure.invalidBundle }
            let handle = try FileHandle(forReadingFrom:path); defer { try? handle.close() }
            var hash = SHA256()
            while let bytes = try handle.read(upToCount:1_048_576), !bytes.isEmpty { try Task.checkCancellation(); hash.update(data:bytes) }
            guard hash.finalize().map({String(format:"%02x",$0)}).joined() == entry.sha256 else { throw Failure.invalidBundle }
        }
        for name in ["Segmentation","FBank","Embedding","PldaRho"] {
            guard lock.files[name+".mlmodelc/weights/weight.bin"] != nil else { throw Failure.invalidBundle }
        }
    }
    private static func decode(_ source: URL, progress: @Sendable (String)->Void) async throws -> [Float] {
        guard source.isFileURL else { throw Failure.invalidAudio }
        let v = try source.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
        guard v.isRegularFile == true, v.isSymbolicLink != true, let size=v.fileSize, (1...536_870_912).contains(size) else { throw Failure.invalidAudio }
        let asset=AVURLAsset(url:source), duration=try await asset.load(.duration).seconds
        guard duration.isFinite, (3...1800).contains(duration) else { throw Failure.resourceBound }
        let tracks=try await asset.loadTracks(withMediaType:.audio)
        guard tracks.count==1,let track=tracks.first else { throw Failure.invalidAudio }
        let reader=try AVAssetReader(asset:asset)
        let output=AVAssetReaderTrackOutput(track:track,outputSettings:[AVFormatIDKey:kAudioFormatLinearPCM,AVSampleRateKey:16_000,AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:32,AVLinearPCMIsFloatKey:true,AVLinearPCMIsBigEndianKey:false,AVLinearPCMIsNonInterleaved:false])
        output.alwaysCopiesSampleData=false
        guard reader.canAdd(output) else { throw Failure.invalidAudio };reader.add(output)
        guard reader.startReading() else { throw Failure.invalidAudio }
        defer { if reader.status == .reading { reader.cancelReading() } }
        var samples:[Float]=[]; samples.reserveCapacity(min(28_800_000,Int(duration*16_000)+16_000));var last=Date()
        while let buffer=output.copyNextSampleBuffer() {
            try Task.checkCancellation()
            guard let description=CMSampleBufferGetFormatDescription(buffer),let format=CMAudioFormatDescriptionGetStreamBasicDescription(description)?.pointee,format.mSampleRate==16_000,format.mChannelsPerFrame==1,format.mBitsPerChannel==32,format.mFormatFlags & kAudioFormatFlagIsFloat != 0,format.mFormatFlags & kAudioFormatFlagIsBigEndian == 0,let block=CMSampleBufferGetDataBuffer(buffer) else { throw Failure.invalidAudio }
            // Do not silently map a discontinuous or offset audio timeline to
            // different video timestamps. Small codec priming offsets fit inside
            // the 150 ms reference boundary padding; larger gaps fail closed.
            let timestamp = CMSampleBufferGetPresentationTimeStamp(buffer).seconds
            guard timestamp.isFinite, abs(timestamp - Double(samples.count)/16_000) <= 0.05 else { throw Failure.invalidTimeline }
            let count=CMBlockBufferGetDataLength(block)
            guard count>0,count<=4_194_304,count%4==0,count/4<=28_800_000-samples.count else { throw Failure.resourceBound }
            var bytes=Data(count:count)
            let status=bytes.withUnsafeMutableBytes { CMBlockBufferCopyDataBytes(block,atOffset:0,dataLength:count,destination:$0.baseAddress!) }
            guard status==kCMBlockBufferNoErr else { throw Failure.invalidAudio }
            let chunk:[Float]=bytes.withUnsafeBytes { raw in (0..<count/4).map { Float(bitPattern:UInt32(littleEndian:raw.loadUnaligned(fromByteOffset:$0*4,as:UInt32.self))) } }
            guard chunk.allSatisfy({ $0.isFinite && abs($0)<=1.01 }) else { throw Failure.invalidAudio }
            samples.append(contentsOf:chunk)
            if Date().timeIntervalSince(last)>=1 { last=Date();progress("Decoded \(Int(Double(samples.count)/16_000)) of \(Int(duration)) seconds for speaker analysis.") }
        }
        guard reader.status == .completed,samples.count>=48_000 else { throw Failure.invalidAudio }
        return samples
    }
}
