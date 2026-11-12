import Foundation
@main struct Checks {
    static func main() throws {
        let groups = try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:12),.init(speaker:"S2",start:5,end:16)],duration:16)
        precondition(groups.count == 2)
        precondition(groups[0].windows[0].end <= 4.85)
        precondition(groups[1].windows[0].start >= 12.15)
        let same = try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:10),.init(speaker:"S1",start:1,end:9)],duration:10)
        precondition(same.count == 1 && same[0].windows[0].seconds == 8)
        let short = try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:1)],duration:3)
        precondition(short.count == 1 && short[0].windows.isEmpty)
        do { _ = try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:.nan,end:10)],duration:10); fatalError("Invalid timing accepted") } catch LocalSpeakerPolicy.Failure.invalidEvidence { }
        print("Local speaker overlap/bounds policy passed. This is not model inference.")
    }
}
