import Foundation

/// Segmentation evidence, never a character identity or proof of music-free speech.
enum LocalSpeakerPolicy {
    struct Segment: Codable, Sendable { let speaker: String; let start: Double; let end: Double }
    struct Window: Codable, Sendable, Equatable { let start: Double; let end: Double; var seconds: Double { end - start } }
    struct Speaker: Codable, Sendable, Equatable { let speaker: String; let windows: [Window] }
    enum Failure: Error { case invalidEvidence, resourceBound }
    static func speakerWindows(_ segments: [Segment], duration: Double) throws -> [Speaker] {
        guard duration.isFinite, (3...1800).contains(duration), segments.count <= 10_000 else { throw Failure.resourceBound }
        guard segments.allSatisfy({ $0.start.isFinite && $0.end.isFinite && $0.start >= 0 && $0.end > $0.start && $0.end <= duration + 0.05 && $0.speaker.range(of: "^[A-Za-z0-9_-]{1,40}$", options: .regularExpression) != nil }) else { throw Failure.invalidEvidence }
        let identities = Set(segments.map(\.speaker)).sorted()
        guard identities.count <= 32 else { throw Failure.resourceBound }
        // Sweep all model boundaries. Overlap is removed from BOTH speakers; the
        // library's exclusiveSegments mode instead assigns overlap to one speaker.
        var events: [(time: Double, speaker: String, delta: Int)] = []
        for s in segments { events.append((s.start,s.speaker,1)); events.append((min(s.end,duration),s.speaker,-1)) }
        events.sort { $0.time < $1.time }
        var active: [String:Int] = [:], spans: [String:[Window]] = [:]
        var prior = 0.0, index = 0
        while index < events.count {
            let time = events[index].time
            if time > prior, active.count == 1, let speaker = active.keys.first {
                var list = spans[speaker] ?? []
                if let last = list.last, abs(last.end - prior) < 0.000001 { list[list.count-1] = Window(start:last.start,end:time) }
                else { list.append(Window(start:prior,end:time)) }
                spans[speaker] = list
            }
            while index < events.count, events[index].time == time {
                let event = events[index]; active[event.speaker,default:0] += event.delta
                if active[event.speaker] == 0 { active.removeValue(forKey:event.speaker) }
                index += 1
            }
            prior = time
        }
        return identities.map { speaker in
            let clean = (spans[speaker] ?? []).map { Window(start:$0.start + 0.15,end:$0.end - 0.15) }.filter { $0.seconds >= 3 }.sorted {
                $0.seconds == $1.seconds ? $0.start < $1.start : $0.seconds > $1.seconds
            }
            // Bound expensive F5 attempts. Separate contiguous turns outrank extra
            // crops from one turn; do not concatenate speech across other speakers.
            let windows = clean.prefix(3).map { Window(start:$0.start,end:min($0.end,$0.start+8)) }
            return Speaker(speaker:speaker,windows:windows)
        }
    }
}
