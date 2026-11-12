import Foundation

/// Independent classifier scores are not mutually exclusive probabilities.
/// Screening can miss contamination and never proves separation or likeness.
enum LocalSoundQualityPolicy {
    static let version = 1
    struct Frame: Codable, Sendable {
        let start: Double; let end: Double
        let speech: Double; let music: Double; let singing: Double
    }
    struct Decision: Codable, Sendable {
        let admitted: Bool
        let reason: String
        let analyzedCoverage: Double
        let speechCoverage: Double
        let peakMusic: Double
        let peakSinging: Double
    }
    static func evaluate(_ frames: [Frame], duration: Double) -> Decision {
        func unknown(_ reason:String) -> Decision {
            Decision(admitted:false,reason:reason,analyzedCoverage:0,speechCoverage:0,peakMusic:0,peakSinging:0)
        }
        guard duration.isFinite, (1...15).contains(duration), !frames.isEmpty, frames.count <= 128 else {
            return unknown("Incomplete local sound evidence; this candidate needs review.")
        }
        guard frames.allSatisfy({ frame in
            frame.start.isFinite && frame.end.isFinite && frame.start >= 0 && frame.end > frame.start && frame.start < duration && frame.end <= duration + 1 &&
            [frame.speech,frame.music,frame.singing].allSatisfy { $0.isFinite && (0...1).contains($0) }
        }) else { return unknown("Invalid local sound evidence; this candidate needs review.") }
        func covered(_ values:[Frame]) -> Double {
            let ranges=values.map { (start:$0.start,end:min($0.end,duration)) }.sorted { $0.start < $1.start }
            var total=0.0, start=0.0, end=0.0
            for range in ranges {
                if range.start > end { total += end-start;start=range.start;end=range.end }
                else { end=max(end,range.end) }
            }
            return min(1,(total+end-start)/duration)
        }
        let coverage=covered(frames), speech=covered(frames.filter { $0.speech >= 0.5 })
        let music=frames.map(\.music).max() ?? 0, singing=frames.map(\.singing).max() ?? 0
        let reason:String
        let admitted:Bool
        if music >= 0.2 || singing >= 0.2 {
            admitted=false;reason="Local classifier found music or singing risk. Candidate retained, not admitted for generation."
        } else if coverage < 0.8 {
            admitted=false;reason="Local classifier did not cover enough of the candidate. Retained for review."
        } else if speech < 0.6 {
            admitted=false;reason="Too little confident speech evidence. Silence, noise or uncertain audio is retained for review."
        } else {
            admitted=true;reason="Candidate passed conservative local sound screening; this is not proof of clean speech or separation."
        }
        return Decision(admitted:admitted,reason:reason,analyzedCoverage:coverage,speechCoverage:speech,peakMusic:music,peakSinging:singing)
    }
}
