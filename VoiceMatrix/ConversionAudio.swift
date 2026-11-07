import Foundation
import AVFoundation
import Accelerate

enum ConversionError: LocalizedError {
    case missingAssets, damagedAssets, invalidAudio, duration, invalidProfile, modelFailure
    var errorDescription: String? {
        switch self {
        case .missingAssets, .damagedAssets: return "The voice-changing files are missing or damaged. Reinstall the complete app."
        case .duration: return "For voice changing, record or import between 1 and 10 seconds of speech."
        case .invalidAudio: return "That recording could not be used. Try a clear recording with speech."
        case .invalidProfile: return "That voice could not start. Try another voice or reinstall the complete app."
        case .modelFailure: return "Your voice could not be changed. Try another voice or a shorter recording."
        }
    }
}
struct LinearSpectrum {
    let frames: Int
    let values: [Float] // frame-major, 513 bins per frame
    var frequencyMajor: [Float] {
        var output = [Float](repeating: 0, count: values.count)
        for frame in 0..<frames { for bin in 0..<513 { output[bin * frames + frame] = values[frame * 513 + bin] } }
        return output
    }
}
enum ConversionAudio {
    static let sampleRate = 22050.0
    static func spectrum(_ samples: [Float]) throws -> LinearSpectrum {
        guard samples.count >= 2560, samples.count <= 256000, samples.allSatisfy(\.isFinite) else { throw ConversionError.invalidAudio }
        let count = samples.count / 256
        guard (10...1000).contains(count), let setup = vDSP_DFT_zop_CreateSetup(nil, 1024, .FORWARD) else { throw ConversionError.invalidAudio }
        defer { vDSP_DFT_DestroySetup(setup) }
        var padded = [Float](repeating: 0, count: samples.count + 768)
        for i in 0..<384 { padded[i] = samples[384 - i] }
        for i in samples.indices { padded[i + 384] = samples[i] }
        for i in 0..<384 { padded[samples.count + 384 + i] = samples[samples.count - 2 - i] }
        let window = (0..<1024).map { Float(0.5 - 0.5 * cos(2 * Double.pi * Double($0) / 1024)) }
        var real = [Float](repeating: 0, count: 1024)
        let imaginary = [Float](repeating: 0, count: 1024)
        var outReal = real; var outImaginary = real
        var result = [Float](); result.reserveCapacity(count * 513)
        for frame in 0..<count {
            for i in 0..<1024 { real[i] = padded[frame * 256 + i] * window[i] }
            real.withUnsafeBufferPointer { r in imaginary.withUnsafeBufferPointer { im in
                outReal.withUnsafeMutableBufferPointer { ro in outImaginary.withUnsafeMutableBufferPointer { io in
                    vDSP_DFT_Execute(setup, r.baseAddress!, im.baseAddress!, ro.baseAddress!, io.baseAddress!)
                } }
            } }
            // Complex forward DFT is unnormalized; unlike real packed FFT there is no x2 scaling.
            for bin in 0..<513 { result.append(sqrt(outReal[bin] * outReal[bin] + outImaginary[bin] * outImaginary[bin] + 1e-6)) }
        }
        return LinearSpectrum(frames: count, values: result)
    }
    static func readMono(_ url: URL) throws -> [Float] {
        let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
        guard file.processingFormat.sampleRate.isFinite,
              (8000...192000).contains(file.processingFormat.sampleRate),
              (1...8).contains(file.processingFormat.channelCount) else { throw ConversionError.invalidAudio }
        let seconds = Double(file.length) / file.processingFormat.sampleRate
        guard seconds >= 1, seconds <= 10.01 else { throw ConversionError.duration }
        guard let input = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)),
              let monoFormat = AVAudioFormat(standardFormatWithSampleRate: file.processingFormat.sampleRate, channels: 1),
              let mono = AVAudioPCMBuffer(pcmFormat: monoFormat, frameCapacity: AVAudioFrameCount(file.length)),
              let target = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1) else { throw ConversionError.invalidAudio }
        try file.read(into: input)
        guard input.frameLength > 0, let channels = input.floatChannelData, let output = mono.floatChannelData?[0] else { throw ConversionError.invalidAudio }
        mono.frameLength = input.frameLength
        let channelCount = Int(input.format.channelCount)
        for i in 0..<Int(input.frameLength) {
            var value: Float = 0
            for channel in 0..<channelCount { value += channels[channel][i] }
            output[i] = value / Float(channelCount)
        }
        var samples: [Float] = []
        if monoFormat.sampleRate == sampleRate { samples = Array(UnsafeBufferPointer(start: output, count: Int(mono.frameLength))) }
        else {
            guard let converter = AVAudioConverter(from: monoFormat, to: target), let buffer = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: 8192) else { throw ConversionError.invalidAudio }
            var cursor = 0; var ended = false; var attempts = 0
            while !ended {
                attempts += 1; guard attempts <= 100 else { throw ConversionError.invalidAudio }
                buffer.frameLength = 0; var conversionError: NSError?
                let status = converter.convert(to: buffer, error: &conversionError) { requested, state in
                    let remaining = Int(mono.frameLength) - cursor
                    guard remaining > 0 else { state.pointee = .endOfStream; return nil }
                    let count = min(Int(requested), remaining)
                    guard count > 0,
                          let chunk = AVAudioPCMBuffer(pcmFormat: monoFormat, frameCapacity: AVAudioFrameCount(count)),
                          let destination = chunk.floatChannelData?[0] else { state.pointee = .noDataNow; return nil }
                    chunk.frameLength = AVAudioFrameCount(count)
                    destination.update(from: output.advanced(by: cursor), count: count)
                    cursor += count; state.pointee = .haveData; return chunk
                }
                if let conversionError { throw conversionError }
                if let values = buffer.floatChannelData?[0], buffer.frameLength > 0 {
                    samples.append(contentsOf: UnsafeBufferPointer(start: values, count: Int(buffer.frameLength)))
                }
                switch status {
                case .endOfStream: ended = true
                case .haveData, .inputRanDry: break
                case .error: throw ConversionError.invalidAudio
                @unknown default: throw ConversionError.invalidAudio
                }
            }
        }
        let expectedCount = Double(mono.frameLength) * sampleRate / monoFormat.sampleRate
        guard abs(Double(samples.count) - expectedCount) <= 64 else { throw ConversionError.invalidAudio }
        guard samples.count >= 22050, samples.count <= 221000, samples.allSatisfy(\.isFinite) else { throw ConversionError.duration }
        let energy = samples.reduce(0.0) { $0 + Double($1) * Double($1) } / Double(samples.count)
        guard energy > 1e-8 else { throw ConversionError.invalidAudio }
        return samples
    }
    static func write(_ samples: [Float], to url: URL) throws {
        guard samples.count >= 2205, samples.allSatisfy(\.isFinite),
              samples.reduce(0.0, { $0 + Double($1) * Double($1) }) / Double(samples.count) > 1e-9,
              let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)),
              let destination = buffer.floatChannelData?[0] else { throw ConversionError.modelFailure }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        for i in samples.indices { destination[i] = max(-1, min(1, samples[i])) }
        var file: AVAudioFile? = try AVAudioFile(forWriting: url, settings: [AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: sampleRate, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        try file?.write(from: buffer); file = nil
        guard try AVAudioFile(forReading: url).length == Int64(samples.count) else { throw ConversionError.modelFailure }
    }
}
