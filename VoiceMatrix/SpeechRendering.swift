import Foundation
import AVFoundation

struct SpeechControls: Equatable, Sendable {
    var speed: Double = 1
    var pitch: Double = 0
    var volume: Double = 1
    var pause: Double = 0.12
    var isValid: Bool {
        speed.isFinite && (0.5...2).contains(speed) &&
        pitch.isFinite && (-12...12).contains(pitch) &&
        volume.isFinite && (0.25...1).contains(volume) &&
        pause.isFinite && (0...1).contains(pause)
    }
    var needsRendering: Bool { speed != 1 || pitch != 0 || volume != 1 }
    var summary: String { String(format: "%.2fx speed · %+.0f semitones · %.0f%% volume · %.2fs joins", speed, pitch, volume * 100, pause) }
}

enum SpeechRenderError: LocalizedError {
    case invalid, stalled, empty
    var errorDescription: String? {
        switch self {
        case .invalid: return "Choose speed 0.5–2x, pitch -12–12 semitones and volume 25–100%."
        case .stalled: return "Audio effects stopped responding. Try normal speed and pitch."
        case .empty: return "Audio effects did not produce usable speech. Your voice reference was kept."
        }
    }
}

// Offline file-to-file effects: saved/shared audio matches the chosen settings.
// This never connects to the microphone or changes reference recordings.
enum SpeechRendering {
    static func render(source: URL, destination: URL, controls: SpeechControls) async throws {
        guard controls.isValid, source.standardizedFileURL != destination.standardizedFileURL else { throw SpeechRenderError.invalid }
        try Task.checkCancellation()
        let input = try AVAudioFile(forReading: source)
        let format = input.processingFormat
        guard input.length > 0, Double(input.length) / format.sampleRate <= 1800.01,
              format.channelCount == 1 else { throw SpeechRenderError.invalid }
        var complete = false
        var output: AVAudioFile?
        defer { output = nil; if !complete { try? FileManager.default.removeItem(at: destination) } }
        if !controls.needsRendering {
            try FileManager.default.copyItem(at: source, to: destination)
            try Task.checkCancellation()
            complete = true
            return
        }
        let engine = AVAudioEngine()
        let player = AVAudioPlayerNode()
        let effect = AVAudioUnitTimePitch()
        effect.rate = Float(controls.speed)
        effect.pitch = Float(controls.pitch * 100)
        engine.attach(player); engine.attach(effect)
        engine.connect(player, to: effect, format: format)
        engine.connect(effect, to: engine.mainMixerNode, format: format)
        engine.mainMixerNode.outputVolume = Float(controls.volume)
        try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096)
        defer { player.stop(); engine.stop(); engine.disableManualRenderingMode() }
        player.scheduleFile(input, at: nil)
        try engine.start()
        player.play()
        output = try AVAudioFile(forWriting: destination, settings: [
            AVFormatIDKey: Int(kAudioFormatLinearPCM), AVSampleRateKey: format.sampleRate,
            AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false
        ])
        guard let buffer = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: 4096) else { throw SpeechRenderError.empty }
        // Include the unit's processing tail so the final word is not clipped.
        let frames = AVAudioFramePosition(ceil(Double(input.length) / controls.speed + max(0.25, effect.latency) * format.sampleRate))
        var stalls = 0
        var energy = 0.0
        var count = 0
        let deadline = Date().addingTimeInterval(600)
        while engine.manualRenderingSampleTime < frames {
            try Task.checkCancellation()
            guard Date() < deadline else { throw SpeechRenderError.stalled }
            let requested = AVAudioFrameCount(min(AVAudioFramePosition(buffer.frameCapacity), frames - engine.manualRenderingSampleTime))
            let status = try engine.renderOffline(requested, to: buffer)
            switch status {
            case .success:
                guard buffer.frameLength > 0, let samples = buffer.floatChannelData?[0] else { throw SpeechRenderError.empty }
                for i in 0..<Int(buffer.frameLength) {
                    guard samples[i].isFinite else { throw SpeechRenderError.empty }
                    samples[i] = max(-0.98, min(0.98, samples[i]))
                    energy += Double(samples[i]) * Double(samples[i]); count += 1
                }
                try output?.write(from: buffer); stalls = 0
            case .cannotDoInCurrentContext, .insufficientDataFromInputNode:
                stalls += 1
                guard stalls < 100 else { throw SpeechRenderError.stalled }
            case .error: throw SpeechRenderError.empty
            @unknown default: throw SpeechRenderError.empty
            }
            await Task.yield()
        }
        try Task.checkCancellation()
        guard count > 0, energy / Double(count) > 1e-8 else { throw SpeechRenderError.empty }
        complete = true
    }
}
