import Foundation
import CryptoKit

/// Inspects a generated WAV before it becomes device evidence.
/// This checks structure and nonzero PCM bytes, NOT speaker identity or audibility.
enum GhostlineWAVInspector {
    struct Facts {
        let sampleRate: Int
        let channels: Int
        let bitsPerSample: Int
        let audioFrames: Int
        let durationSeconds: Double
        let sampleFormat: Int
        // SHA-256 of the uncompressed samples, not the WAV container.
        // Technical evidence only; not proof of identity or audibility.
        let pcmSHA256: String
    }

    enum Failure: Error, LocalizedError {
        case invalid(String)
        var errorDescription: String? {
            if case .invalid(let detail) = self { return detail }
            return "Invalid WAV"
        }
    }

    private static func u16(_ bytes: Data, _ at: Int) -> Int {
        Int(bytes[at]) | (Int(bytes[at + 1]) << 8)
    }

    private static func u32(_ bytes: Data, _ at: Int) -> Int {
        Int(bytes[at]) | (Int(bytes[at + 1]) << 8) |
        (Int(bytes[at + 2]) << 16) | (Int(bytes[at + 3]) << 24)
    }

    static func inspect(_ bytes: Data) throws -> Facts {
        guard bytes.count >= 44,
              bytes.prefix(4).elementsEqual("RIFF".utf8),
              bytes[8..<12].elementsEqual("WAVE".utf8) else {
            throw Failure.invalid("Output is not a RIFF/WAVE recording")
        }
        let riffEnd = u32(bytes, 4) + 8
        guard riffEnd <= bytes.count, riffEnd >= 44 else {
            throw Failure.invalid("Truncated or malformed WAV container")
        }
        var cursor = 12
        var format: (code: Int, channels: Int, rate: Int, alignment: Int, bits: Int)?
        var audioRange: Range<Int>?

        while cursor + 8 <= riffEnd {
            let payloadLength = u32(bytes, cursor + 4)
            let start = cursor + 8
            guard payloadLength <= riffEnd - start else {
                throw Failure.invalid("WAV chunk exceeds the RIFF container")
            }
            let end = start + payloadLength
            let name = String(decoding: bytes[cursor..<(cursor + 4)], as: UTF8.self)
            if name == "fmt " {
                guard payloadLength >= 16 else {
                    throw Failure.invalid("Incomplete WAV sample-format chunk")
                }
                format = (u16(bytes, start), u16(bytes, start + 2),
                          u32(bytes, start + 4), u16(bytes, start + 12),
                          u16(bytes, start + 14))
            } else if name == "data" && audioRange == nil {
                audioRange = start..<end
            }
            let padding = payloadLength & 1
            guard end + padding <= riffEnd else {
                throw Failure.invalid("Truncated WAV chunk padding")
            }
            cursor = end + padding
        }

        guard let fmt = format, let samples = audioRange else {
            throw Failure.invalid("WAV has no sample format or PCM data")
        }
        guard (fmt.code == 1 && [16, 24, 32].contains(fmt.bits)) ||
              (fmt.code == 3 && [32, 64].contains(fmt.bits)),
              (1...8).contains(fmt.channels), (8_000...192_000).contains(fmt.rate),
              fmt.alignment == fmt.channels * (fmt.bits / 8),
              samples.count >= fmt.alignment,
              samples.count % fmt.alignment == 0 else {
            throw Failure.invalid("Unsupported or inconsistent WAV sample format")
        }
        // IEEE floats have both +0 and -0; raw nonzero bytes do not
        // establish a non-silent sample. Reject NaN/Inf before evidence.
        var hasSignal = false
        if fmt.code == 3 {
            let width = fmt.bits / 8
            let exponentMask: UInt64 = width == 4 ? 0x7f80_0000 : 0x7ff0_0000_0000_0000
            let valueMask: UInt64 = width == 4 ? 0x7fff_ffff : 0x7fff_ffff_ffff_ffff
            for offset in stride(from: samples.lowerBound, to: samples.upperBound, by: width) {
                var word: UInt64 = 0
                for i in 0..<width { word |= UInt64(bytes[offset + i]) << (i * 8) }
                guard (word & exponentMask) != exponentMask else {
                    throw Failure.invalid("WAV contains NaN or infinite floating-point samples")
                }
                if (word & valueMask) != 0 { hasSignal = true }
            }
        } else {
            hasSignal = bytes[samples].contains(where: { $0 != 0 })
        }
        guard hasSignal else {
            throw Failure.invalid("WAV contains only zero-valued audio samples")
        }
        // A Data slice avoids duplicating a large audio buffer in memory.
        let pcmDigest = SHA256.hash(data: bytes[samples])
            .map { String(format: "%02x", $0) }.joined()
        let frames = samples.count / fmt.alignment
        return Facts(sampleRate: fmt.rate, channels: fmt.channels,
                     bitsPerSample: fmt.bits, audioFrames: frames,
                     durationSeconds: Double(frames) / Double(fmt.rate),
                     sampleFormat: fmt.code, pcmSHA256: pcmDigest)
    }
}
