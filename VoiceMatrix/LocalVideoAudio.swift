import Foundation
import AVFoundation
import CoreMedia

/// A bounded local extraction primitive, not diarization or identity verification.
/// The caller retains the source and decides when a reviewed candidate is admitted.
enum LocalVideoAudio {
    struct Reference: Sendable {
        let wave: Data
        let seconds: Double
        let rms: Double
        let clippedFraction: Double
    }
    enum Failure: Error { case localFileRequired, bounds, unreadable, unusableAudio }

    static func extract(source: URL, start: Double, seconds: Double) async throws -> Reference {
        guard source.isFileURL else { throw Failure.localFileRequired }
        guard start.isFinite, seconds.isFinite, start >= 0, (0.5...15).contains(seconds), start + seconds <= 1800 else { throw Failure.bounds }
        let values = try source.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true,
              let size = values.fileSize, size > 0, size <= 536_870_912 else { throw Failure.unreadable }
        try Task.checkCancellation()
        let asset = AVURLAsset(url: source)
        let duration = try await asset.load(.duration).seconds
        guard duration.isFinite, duration > 0, duration <= 1800, start + seconds <= duration + 0.001 else { throw Failure.bounds }
        let tracks = try await asset.loadTracks(withMediaType: .audio)
        // Multiple tracks require an explicit selection; do not silently mix speakers.
        guard tracks.count == 1, let track = tracks.first else { throw Failure.unusableAudio }
        let reader = try AVAssetReader(asset: asset)
        reader.timeRange = CMTimeRange(start: CMTime(seconds: start, preferredTimescale: 24_000), duration: CMTime(seconds: seconds, preferredTimescale: 24_000))
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 24_000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false
        ])
        output.alwaysCopiesSampleData = false
        guard reader.canAdd(output) else { throw Failure.unreadable }
        reader.add(output)
        guard reader.startReading() else { throw Failure.unreadable }
        defer { if reader.status == .reading { reader.cancelReading() } }
        var pcm = Data()
        while let sample = output.copyNextSampleBuffer() {
            try Task.checkCancellation()
            guard let description = CMSampleBufferGetFormatDescription(sample),
                  let format = CMAudioFormatDescriptionGetStreamBasicDescription(description)?.pointee,
                  format.mFormatID == kAudioFormatLinearPCM, format.mSampleRate == 24_000,
                  format.mChannelsPerFrame == 1, format.mBitsPerChannel == 16,
                  format.mFormatFlags & kAudioFormatFlagIsFloat == 0,
                  format.mFormatFlags & kAudioFormatFlagIsSignedInteger != 0,
                  format.mFormatFlags & kAudioFormatFlagIsBigEndian == 0,
                  let block = CMSampleBufferGetDataBuffer(sample) else { throw Failure.unusableAudio }
            let count = CMBlockBufferGetDataLength(block)
            guard count > 0, count % 2 == 0, count <= 720_000 - pcm.count else { throw Failure.bounds }
            var bytes = Data(count: count)
            let status = bytes.withUnsafeMutableBytes { buffer in
                CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: count, destination: buffer.baseAddress!)
            }
            guard status == kCMBlockBufferNoErr else { throw Failure.unreadable }
            pcm.append(bytes)
        }
        try Task.checkCancellation()
        guard reader.status == .completed, (24_000...720_000).contains(pcm.count) else { throw Failure.unreadable }
        var energy = 0.0, clipped = 0
        for i in stride(from: 0, to: pcm.count, by: 2) {
            let value = Int16(bitPattern: UInt16(pcm[i]) | UInt16(pcm[i + 1]) << 8)
            let scaled = Double(value) / 32768
            energy += scaled * scaled
            if abs(Int(value)) >= 32760 { clipped += 1 }
        }
        let frames = Double(pcm.count / 2), rms = sqrt(energy / frames)
        let clipping = Double(clipped) / frames
        guard rms >= 0.0002, clipping < 0.01 else { throw Failure.unusableAudio }
        var wave = Data()
        func tag(_ value: String) { wave.append(contentsOf: value.utf8) }
        func u16(_ value: UInt16) { var little = value.littleEndian; withUnsafeBytes(of: &little) { wave.append(contentsOf: $0) } }
        func u32(_ value: UInt32) { var little = value.littleEndian; withUnsafeBytes(of: &little) { wave.append(contentsOf: $0) } }
        tag("RIFF"); u32(UInt32(pcm.count + 36)); tag("WAVE"); tag("fmt "); u32(16)
        u16(1); u16(1); u32(24_000); u32(48_000); u16(2); u16(16)
        tag("data"); u32(UInt32(pcm.count)); wave.append(pcm)
        return Reference(wave: wave, seconds: frames / 24_000, rms: rms, clippedFraction: clipping)
    }
}
