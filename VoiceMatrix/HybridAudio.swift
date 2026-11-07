import Foundation
import AVFoundation

enum SpeechTextChunks {
    static func split(_ text: String) -> [String] {
        var chunks: [String] = []; var words: [String] = []
        for word in text.split(whereSeparator: \.isWhitespace) {
            words.append(String(word))
            if words.count >= 12 || word.last.map({ ".!?;".contains($0) }) == true {
                chunks.append(words.joined(separator: " ")); words.removeAll(keepingCapacity: true)
            }
        }
        if !words.isEmpty { chunks.append(words.joined(separator: " ")) }
        return chunks
    }
}
enum ConvertedAudioAssembler {
    static func join(_ urls: [URL], to output: URL) throws -> Double {
        guard !urls.isEmpty else { throw StudioError.emptyAudio }
        var writer: AVAudioFile? = try AVAudioFile(forWriting: output, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: 22050.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        var frames: Int64 = 0
        do {
            for url in urls {
                try Task.checkCancellation()
                let source = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
                guard source.processingFormat.sampleRate == 22050, source.processingFormat.channelCount == 1,
                      let buffer = AVAudioPCMBuffer(pcmFormat: source.processingFormat, frameCapacity: 8192) else { throw StudioError.emptyAudio }
                while source.framePosition < source.length {
                    try Task.checkCancellation()
                    try source.read(into: buffer)
                    guard buffer.frameLength > 0 else { throw StudioError.emptyAudio }
                    try writer?.write(from: buffer); frames += Int64(buffer.frameLength)
                }
            }
            writer = nil
            guard try AVAudioFile(forReading: output).length == frames else { throw StudioError.emptyAudio }
            return Double(frames) / 22050
        } catch { writer = nil; try? FileManager.default.removeItem(at: output); throw error }
    }
}
