import Foundation

/// No authentication, JavaScript execution, challenge solving or alternate clients.
enum LocalMediaURLPolicy {
    enum Role { case page, stream, direct }
    enum Kind: String, Codable { case combined, video, audio }
    struct Part: Codable { let url: URL; let kind: Kind; let ext: String }
    enum Failure: LocalizedError {
        case url, restricted, unsupported, response, bounds, storage, changed
        var errorDescription: String? {
            switch self {
            case .url: return "Use an HTTPS YouTube link or a direct media link from upload.wikimedia.org or archive.org. Other hosts, credentials and redirects outside the approved hosts are not supported."
            case .restricted: return "The website requires access, sign-in or verification, or this is a live/restricted video. No bypass or third-party downloader was used. Import an authorized local file instead."
            case .unsupported: return "This page does not provide supported public MP4/AAC streams directly. Encrypted signatures, streaming manifests and website challenges are not supported. Import an authorized local file instead."
            case .response: return "The website did not return a complete supported media response. Partial files were retained; Retry starts a new download without appending unrelated bytes."
            case .bounds: return "This acquisition exceeded its byte, duration or time limit. Files were retained; use a shorter authorized local clip."
            case .storage: return "Not enough safe storage remains for this acquisition. Existing sources and voices were kept."
            case .changed: return "A retained acquisition file changed or is missing. It was not silently replaced. Start a new job after reviewing retained files."
            }
        }
    }
    static let maximumBytes: Int64 = 536_870_912
    static func byteBudget(retained:Int64,free:Int64,reserveForMerge:Bool,completedSourceBytes:Int64 = 0) throws -> Int64 {
        guard retained>=0,free>=0,completedSourceBytes>=0,completedSourceBytes<=maximumBytes else { throw Failure.storage }
        let room=min(2_000_000_000-retained,free-800_000_000)
        guard room>0 else { throw Failure.storage }
        // Completed original tracks also need a future merged copy. Page/direct
        // downloads and the final merge itself must not reserve a second merge.
        let available=reserveForMerge ? (room-completedSourceBytes)/2 : room
        guard available>0 else { throw Failure.storage }
        return min(maximumBytes,available)
    }
    static func validate(_ url: URL, role: Role) throws {
        guard url.scheme?.lowercased() == "https", url.user == nil, url.password == nil,
              url.port == nil || url.port == 443, url.fragment == nil,
              url.absoluteString.utf8.count <= 16_384,
              let host = url.host?.lowercased(), !host.hasSuffix("."), !host.contains(":") else { throw Failure.url }
        let permitted: Bool
        switch role {
        case .page: permitted = ["www.youtube.com","youtube.com","m.youtube.com","youtu.be"].contains(host)
        case .stream: permitted = host == "googlevideo.com" || host.hasSuffix(".googlevideo.com")
        case .direct: permitted = host == "upload.wikimedia.org" || archiveHost(host)
        }
        guard permitted else { throw Failure.url }
    }
    private static func archiveHost(_ host:String) -> Bool {
        // Internet Archive's own MDAPI documentation names this storage-node form.
        host == "archive.org" || host.range(of:"^ia[0-9]{6}\\.us\\.archive\\.org$",options:.regularExpression) != nil
    }
    static func validateRedirect(from:URL,to:URL,role:Role) throws {
        try validate(from,role:role);try validate(to,role:role)
        if role == .direct {
            guard let source=from.host?.lowercased(),let target=to.host?.lowercased(),
                  source == target || (archiveHost(source) && archiveHost(target)) else { throw Failure.url }
        }
    }
    static func input(_ text: String) throws -> URL {
        guard text.utf8.count <= 16_384, let url=URL(string:text.trimmingCharacters(in:.whitespacesAndNewlines)) else { throw Failure.url }
        if let id = try? videoID(url) { return URL(string:"https://www.youtube.com/watch?v=" + id)! }
        try validate(url,role:.direct)
        guard ["mp4","mov","m4v","m4a","wav","aac","caf"].contains(url.pathExtension.lowercased()) else { throw Failure.unsupported }
        return url
    }
    static func videoID(_ url: URL) throws -> String {
        try validate(url,role:.page)
        let components=URLComponents(url:url,resolvingAgainstBaseURL:false)
        let path=url.path.split(separator:"/").map(String.init)
        let id: String?
        if url.host?.lowercased() == "youtu.be",path.count == 1 { id=path.first }
        else if path.count == 2,["shorts","embed","live"].contains(path[0]) { id=path[1] }
        else if url.path == "/watch" {
            let values=(components?.queryItems ?? []).filter { $0.name == "v" }
            guard values.count == 1 else { throw Failure.url };id=values[0].value
        } else { id=nil }
        guard let id,id.range(of:"^[A-Za-z0-9_-]{11}$",options:.regularExpression) != nil else { throw Failure.url }
        return id
    }
    static func youtubePlan(_ page: Data, videoID: String) throws -> [Part] {
        guard page.count <= 4_000_000,let text=String(data:page,encoding:.utf8),
              let marker=text.range(of:"ytInitialPlayerResponse"),
              let opening=text[marker.upperBound...].firstIndex(of:"{") else { throw Failure.unsupported }
        // Balanced JSON scanner, not JavaScript evaluation. Braces inside strings are ignored.
        var depth=0,inString=false,escaped=false,end:String.Index?
        for i in text[opening...].indices {
            let c=text[i]
            if inString { if escaped { escaped=false } else if c == "\\" { escaped=true } else if c == "\"" { inString=false };continue }
            if c == "\"" { inString=true }
            else if c == "{" { depth += 1 }
            else if c == "}" { depth -= 1;if depth == 0 { end=text.index(after:i);break } }
            guard depth <= 128 else { throw Failure.bounds }
        }
        guard let end,let object=try JSONSerialization.jsonObject(with:Data(text[opening..<end].utf8)) as? [String:Any],
              let status=object["playabilityStatus"] as? [String:Any],status["status"] as? String == "OK",
              let details=object["videoDetails"] as? [String:Any],details["videoId"] as? String == videoID,
              details["isLiveContent"] as? Bool == false else { throw Failure.restricted }
        guard let secondsText=details["lengthSeconds"] as? String,let seconds=Double(secondsText),seconds.isFinite,(3...1800).contains(seconds) else { throw Failure.bounds }
        if let micro=(object["microformat"] as? [String:Any])?["playerMicroformatRenderer"] as? [String:Any],micro["isFamilySafe"] as? Bool == false { throw Failure.restricted }
        guard let streams=object["streamingData"] as? [String:Any] else { throw Failure.unsupported }
        var choices:[(part:Part,height:Int,size:Int64)] = []
        let formats=(streams["formats"] as? [[String:Any]] ?? []) + (streams["adaptiveFormats"] as? [[String:Any]] ?? [])
        guard formats.count <= 300 else { throw Failure.bounds }
        for f in formats {
            guard f["signatureCipher"] == nil,f["cipher"] == nil,f["drmFamilies"] == nil,
                  let raw=f["url"] as? String,let url=URL(string:raw),(try? validate(url,role:.stream)) != nil,
                  let mime=f["mimeType"] as? String,let sizeText=f["contentLength"] as? String,let size=Int64(sizeText),size>0,size<=maximumBytes else { continue }
            let height=f["height"] as? Int ?? 0
            let kind:Kind
            if mime.hasPrefix("audio/mp4"),mime.contains("mp4a") { kind = .audio }
            else if mime.hasPrefix("video/mp4"),mime.contains("avc1"),(1...720).contains(height) { kind = mime.contains("mp4a") ? .combined : .video }
            else { continue }
            choices.append((Part(url:url,kind:kind,ext:kind == .audio ? "m4a":"mp4"),height,size))
        }
        choices.sort { $0.size < $1.size }
        if let combined=choices.first(where:{$0.part.kind == .combined}) { return [combined.part] }
        if let video=choices.first(where:{$0.part.kind == .video}),let audio=choices.first(where:{$0.part.kind == .audio}),video.size+audio.size<=maximumBytes { return [video.part,audio.part] }
        throw Failure.unsupported
    }
}
