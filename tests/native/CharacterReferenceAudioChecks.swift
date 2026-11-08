import Foundation
import AVFoundation

@main struct CharacterReferenceAudioChecks {
    static func main() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at: url) }
        let rate = 24000.0, frames = 240480
        let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1)!
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames))!
        buffer.frameLength = AVAudioFrameCount(frames)
        for i in 0..<frames { buffer.floatChannelData![0][i] = Float(sin(Double(i) * 2 * .pi * 180 / rate) * 0.1) }
        var file: AVAudioFile? = try AVAudioFile(forWriting: url, settings: [AVFormatIDKey:Int(kAudioFormatLinearPCM),AVSampleRateKey:rate,AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:16,AVLinearPCMIsFloatKey:false])
        try file!.write(from: buffer); file = nil
        do { _ = try ConversionAudio.readMono(url); fatalError("A source recording over10seconds was accepted") }
        catch ConversionError.duration { }
        let target = try ConversionAudio.readMono(url, minimumSeconds: 0.5, isReference: true)
        precondition(abs(target.count - 220500) <= 64, "Reference extraction must bound reads to10seconds")
        precondition(!target.isEmpty && target.allSatisfy(\.isFinite))
        print("Long reference input safely bounded; source duration gate unchanged")
    }
}
