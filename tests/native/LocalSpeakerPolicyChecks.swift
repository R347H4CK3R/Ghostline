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
        let long = try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:15)],duration:15)
        precondition(long[0].windows.count == 3)
        precondition(long[0].windows.map { Int($0.seconds.rounded()) } == [8,4,3])
        precondition(long[0].windows[1].end == 14.85 && long[0].windows[2].end == 14.85)
        let turns:[LocalSpeakerPolicy.Segment] = [.init(speaker:"S1",start:0,end:10),.init(speaker:"S1",start:12,end:20),.init(speaker:"S1",start:22,end:28)]
        let distinct=try LocalSpeakerPolicy.speakerWindows(turns,duration:28)[0].windows
        precondition(distinct.count == 3 && distinct.map(\.start) == [0.15,12.15,22.15])
        let repeated=try LocalSpeakerPolicy.speakerWindows(Array(turns.reversed()),duration:28)
        precondition(repeated[0].windows == distinct)
        let two=try LocalSpeakerPolicy.speakerWindows(Array(turns.prefix(2)),duration:28)[0].windows
        precondition(two.count == 3 && two[0].start == 0.15 && two[1].start == 12.15 && abs(two[2].seconds-4)<0.000001)
        let legacy=try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:15)],duration:15,includeFallbacks:false)
        precondition(legacy[0].windows.count==1)
        do { _=try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:10.01,end:10.04)],duration:10);fatalError("Start past duration accepted") } catch LocalSpeakerPolicy.Failure.invalidEvidence { }
        let exact=try LocalSpeakerPolicy.speakerWindows([.init(speaker:"S1",start:0,end:3.3)],duration:4)[0].windows
        precondition(exact.count <= 1)
        for group in groups {
            precondition(group.windows.count <= 3)
            for window in group.windows {
                precondition(window.seconds >= 3)
                if group.speaker == "S1" { precondition(window.start >= 0.15 && window.end <= 4.85) }
                else { precondition(window.start >= 12.15 && window.end <= 15.85) }
            }
        }
        precondition(long[0].windows.enumerated().allSatisfy { index,window in !long[0].windows.prefix(index).contains(window) })
        print("Local speaker overlap/bounds policy passed. This is not model inference.")
    }
}
