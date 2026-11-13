import Foundation
import AVFoundation
import CryptoKit
@preconcurrency import CoreML
import FluidAudio

/// Opt-in diagnostic service. Does not write files, import voices or decide likeness.
/// Owns one comparison at a time, with private immutable WAV snapshots supplied by caller.
actor SpeakerSimilarityService {
    enum Failure: Error { case busy, invalidWave, resourceBound, conversion, embedding }
    struct Report: Codable, Sendable {
        let schemaVersion: Int
        let referenceSHA256: String
        let generatedSHA256: String
        let modelRevision: String
        let algorithm: String
        let referenceSeconds: Double
        let generatedSeconds: Double
        let cosineSimilarity: Double
        let likenessVerified = false
        let identityVerified = false
    }
    private var busy = false
    static let modelRevision = "df2625ac79a7ac6b65ad868fee6d80f320da4232"
    func compare(referenceWAV: Data, generatedWAV: Data, bundle: URL,
                 progress: @escaping @Sendable (String)->Void = {_ in}) async throws -> Report {
        guard !busy else { throw Failure.busy }
        busy=true;defer { busy=false }
        // Data uses value semantics: hashes and decoded samples refer to the same snapshots.
        let worker=Task.detached(priority:.utility) {
            try Task.checkCancellation()
            let reference=try Self.samples(referenceWAV, maximumSeconds: 30)
            let generated=try Self.samples(generatedWAV, maximumSeconds: 30)
            progress("Checking bundled speaker models for a similarity diagnostic, not likeness verification.")
            let manager=try Self.makeManager(bundle)
            try Task.checkCancellation()
            progress("Measuring the reference voice embedding locally.")
            let a=try await manager.embedSpans(audioSource:ArrayAudioSampleSource(samples:reference),spans:[0..<Double(reference.count)/16000])
            try Task.checkCancellation()
            progress("Measuring the generated voice embedding locally.")
            let b=try await manager.embedSpans(audioSource:ArrayAudioSampleSource(samples:generated),spans:[0..<Double(generated.count)/16000])
            try Task.checkCancellation()
            guard a.count==1,b.count==1 else { throw Failure.embedding }
            let score=try SpeakerSimilarityPolicy.cosine(a[0],b[0])
            return Report(schemaVersion:1,referenceSHA256:Self.digest(referenceWAV),generatedSHA256:Self.digest(generatedWAV),modelRevision:Self.modelRevision,algorithm:"bundled-raw256-l2-cosine-v1",referenceSeconds:Double(reference.count)/16000,generatedSeconds:Double(generated.count)/16000,cosineSimilarity:score)
        }
        return try await withTaskCancellationHandler { try await worker.value } onCancel: { worker.cancel() }
    }
    private static func digest(_ data: Data)->String { SHA256.hash(data:data).map {String(format:"%02x",$0)}.joined() }
    private static func makeManager(_ bundle: URL) throws -> OfflineDiarizerManager {
        try LocalSpeakerDiarization.verify(bundle)
        func model(_ name:String, cpuOnly:Bool=false) throws -> MLModel {
            try Task.checkCancellation()
            let c=MLModelConfiguration();c.computeUnits=cpuOnly ? .cpuOnly : .all
            return try MLModel(contentsOf:bundle.appendingPathComponent(name+".mlmodelc"),configuration:c)
        }
        let data=try Data(contentsOf:bundle.appendingPathComponent("plda-parameters.json"))
        guard let o=try JSONSerialization.jsonObject(with:data) as? [String:Any],let ts=o["tensors"] as? [String:Any],let psi=ts["psi"] as? [String:Any],let b64=psi["data_base64"] as? String,let bytes=Data(base64Encoded:b64),bytes.count==512 else { throw Failure.embedding }
        let values:[Double]=bytes.withUnsafeBytes { raw in (0..<128).map { Double(Float(bitPattern:UInt32(littleEndian:raw.loadUnaligned(fromByteOffset:$0*4,as:UInt32.self)))) } }
        guard values.allSatisfy({$0.isFinite && $0>=0}) else { throw Failure.embedding }
        let models=try OfflineDiarizerModels(segmentationModel:model("Segmentation"),fbankModel:model("FBank",cpuOnly:true),embeddingModel:model("Embedding"),pldaRhoModel:model("PldaRho"),pldaPsi:values,compilationDuration:0)
        var config=OfflineDiarizerConfig();config.embedding.batchSize=1;config.segmentation.batchSize=1
        let manager=OfflineDiarizerManager(config:config);manager.initialize(models:models)
        return manager
    }
    /// Strict in-memory PCM16 WAV parsing avoids hash/decode path races or temporary source copies.
    private static func samples(_ source:Data, maximumSeconds:Double) throws -> [Float] {
        guard (44...4_194_304).contains(source.count) else { throw Failure.resourceBound }
        let data=Data(source) // Normalize only after bounding the snapshot allocation.
        func tag(_ n:Int)->String { String(decoding:data[n..<n+4],as:UTF8.self) }
        func u16(_ n:Int)->Int { Int(data[n]) | Int(data[n+1])<<8 }
        func u32(_ n:Int)->Int { u16(n) | u16(n+2)<<16 }
        guard tag(0)=="RIFF",tag(8)=="WAVE",u32(4)+8==data.count else { throw Failure.invalidWave }
        var cursor=12,rate:Int?,pcm:Range<Int>?,chunks=0
        while cursor+8<=data.count {
            chunks+=1;guard chunks<=64 else { throw Failure.resourceBound }
            let kind=tag(cursor),size=u32(cursor+4),start=cursor+8
            guard size<=data.count-start else { throw Failure.invalidWave }
            if kind=="fmt " {
                guard rate==nil,size>=16,u16(start)==1,u16(start+2)==1,u16(start+14)==16,u16(start+12)==2 else { throw Failure.invalidWave }
                let hz=u32(start+4);guard [16000,22050,24000,32000,40000,44100,48000].contains(hz),u32(start+8)==hz*2 else { throw Failure.invalidWave };rate=hz
            } else if kind=="data" {
                guard pcm==nil,size>0,size%2==0 else { throw Failure.invalidWave };pcm=start..<start+size
            }
            cursor=start+size+size%2
        }
        guard cursor==data.count,let rate,let pcm else { throw Failure.invalidWave }
        let count=pcm.count/2,seconds=Double(count)/Double(rate)
        guard (3...maximumSeconds).contains(seconds) else { throw Failure.resourceBound }
        try Task.checkCancellation()
        guard let inputFormat=AVAudioFormat(commonFormat:.pcmFormatFloat32,sampleRate:Double(rate),channels:1,interleaved:false),let input=AVAudioPCMBuffer(pcmFormat:inputFormat,frameCapacity:AVAudioFrameCount(count)),let channel=input.floatChannelData?[0] else { throw Failure.conversion }
        input.frameLength=AVAudioFrameCount(count)
        var energy=0.0
        for i in 0..<count { let x=Float(Int16(bitPattern:UInt16(u16(pcm.lowerBound+i*2))))/32768;channel[i]=x;energy+=Double(x)*Double(x) }
        guard sqrt(energy/Double(count))>0.0001 else { throw Failure.invalidWave }
        guard let format=AVAudioFormat(commonFormat:.pcmFormatFloat32,sampleRate:16000,channels:1,interleaved:false),let converter=AVAudioConverter(from:inputFormat,to:format) else { throw Failure.conversion }
        var used=false,answer:[Float]=[]
        for _ in 0..<128 {
            try Task.checkCancellation()
            guard let output=AVAudioPCMBuffer(pcmFormat:format,frameCapacity:4096) else { throw Failure.conversion }
            var error:NSError?
            let state=converter.convert(to:output,error:&error) { _,status in
                if used { status.pointee = .endOfStream;return nil }
                used=true;status.pointee = .haveData;return input
            }
            guard error==nil,state != .error,let samples=output.floatChannelData?[0] else { throw Failure.conversion }
            answer.append(contentsOf:UnsafeBufferPointer(start:samples,count:Int(output.frameLength)))
            guard answer.count<=480_512,answer.allSatisfy({$0.isFinite}) else { throw Failure.resourceBound }
            if state == .endOfStream { guard answer.count>=48_000 else { throw Failure.invalidWave };return answer }
            guard state == .haveData else { throw Failure.conversion }
        }
        throw Failure.resourceBound
    }
}
