import Foundation
@main struct Checks {
    static func rejected(_ body:() throws -> Void) {
        do { try body();fatalError("Unsafe acquisition evidence accepted") } catch { }
    }
    static func main() throws {
        let normalized=try LocalMediaURLPolicy.input("https://youtu.be/abcdefghijk?t=4")
        precondition(normalized.absoluteString == "https://www.youtube.com/watch?v=abcdefghijk")
        for raw in ["http://youtube.com/watch?v=abcdefghijk","https://youtube.com.evil.test/watch?v=abcdefghijk","https://user:pass@youtube.com/watch?v=abcdefghijk","https://127.0.0.1/a.mp4","https://[::1]/a.mp4","https://www.youtube.com:444/watch?v=abcdefghijk"] {
            rejected { _ = try LocalMediaURLPolicy.input(raw) }
        }
        let from=URL(string:"https://archive.org/download/example/a.mp4")!
        try LocalMediaURLPolicy.validateRedirect(from:from,to:URL(string:"https://ia800308.us.archive.org/21/items/example/a.mp4")!,role:.direct)
        for raw in ["https://ia800308.us.archive.org.evil.test/a.mp4","https://evil.archive.org/a.mp4","https://upload.wikimedia.org/a.mp4","https://10.0.0.1/a.mp4"] {
            rejected { try LocalMediaURLPolicy.validateRedirect(from:from,to:URL(string:raw)!,role:.direct) }
        }
        let finalBudget=try LocalMediaURLPolicy.byteBudget(retained:1_500_000_000,free:1_300_000_000,reserveForMerge:false)
        let nextBudget=try LocalMediaURLPolicy.byteBudget(retained:1_400_000_000,free:1_400_000_000,reserveForMerge:true,completedSourceBytes:400_000_000)
        precondition(finalBudget==500_000_000 && nextBudget==100_000_000)
        rejected { _ = try LocalMediaURLPolicy.byteBudget(retained:2_000_000_000,free:2_000_000_000,reserveForMerge:false) }
        var video:[String:Any] = ["url":"https://rr1.googlevideo.com/video","mimeType":"video/mp4; codecs=\"avc1.42, mp4a.40.2\"","contentLength":"100","height":360]
        let details:[String:Any] = ["videoId":"abcdefghijk","isLiveContent":false,"lengthSeconds":"12"]
        func page(_ formats:[[String:Any]],status:String="OK",live:Bool=false) throws -> Data {
            var d=details;d["isLiveContent"]=live
            let object:[String:Any] = ["playabilityStatus":["status":status],"videoDetails":d,"streamingData":["adaptiveFormats":formats]]
            return Data(("ytInitialPlayerResponse = " + String(decoding:try JSONSerialization.data(withJSONObject:object),as:UTF8.self)).utf8)
        }
        let progressive=try LocalMediaURLPolicy.youtubePlan(page([video]),videoID:"abcdefghijk")
        precondition(progressive.count==1 && progressive[0].kind == .combined)
        video["mimeType"]="video/mp4; codecs=\"avc1.42\""
        let audio:[String:Any] = ["url":"https://rr1.googlevideo.com/audio","mimeType":"audio/mp4; codecs=\"mp4a.40.2\"","contentLength":"100"]
        let adaptive=try LocalMediaURLPolicy.youtubePlan(page([video,audio]),videoID:"abcdefghijk")
        precondition(adaptive.map(\.kind)==[.video,.audio])
        rejected { _ = try LocalMediaURLPolicy.youtubePlan(page([video,audio],status:"LOGIN_REQUIRED"),videoID:"abcdefghijk") }
        rejected { _ = try LocalMediaURLPolicy.youtubePlan(page([video,audio],live:true),videoID:"abcdefghijk") }
        rejected { _ = try LocalMediaURLPolicy.youtubePlan(page([video,audio]),videoID:"mismatched") }
        video.removeValue(forKey:"url");video["signatureCipher"]="not-executed"
        rejected { _ = try LocalMediaURLPolicy.youtubePlan(page([video]),videoID:"abcdefghijk") }
        print("Native acquisition URL/parser/budget policy passed; no website/network inference is claimed.")
    }
}
