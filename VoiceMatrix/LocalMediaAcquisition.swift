import Foundation
import AVFoundation
import CryptoKit

enum LocalMediaAcquisition {
    struct Result: Codable { let file: String; let sha256: String; let bytes: Int64 }
    private struct Receipt: Codable { let input: URL; let parts: [LocalMediaURLPolicy.Part]; var files: [Result]; var merged: Result? }
    typealias Progress = @Sendable (String) -> Void
    static func acquire(input: URL, folder: URL, progress: @escaping Progress) async throws -> Result {
        do { return try await acquireChecked(input:input,folder:folder,progress:progress) }
        catch is CancellationError { throw CancellationError() }
        catch let failure as LocalMediaURLPolicy.Failure { throw failure }
        catch { throw LocalMediaURLPolicy.Failure.response }
    }
    private static func acquireChecked(input:URL,folder:URL,progress:@escaping Progress) async throws -> Result {
        let normalized=try LocalMediaURLPolicy.input(input.absoluteString)
        _ = try remainingBudget(folder:folder, reserveForMerge:false)
        let receiptURL=folder.appendingPathComponent("acquisition.json")
        var receipt: Receipt
        if FileManager.default.fileExists(atPath:receiptURL.path) {
            let values=try receiptURL.resourceValues(forKeys:[.fileSizeKey,.isSymbolicLinkKey])
            guard values.isSymbolicLink != true,(values.fileSize ?? Int.max)<=131_072 else { throw LocalMediaURLPolicy.Failure.changed }
            receipt=try JSONDecoder().decode(Receipt.self,from:Data(contentsOf:receiptURL))
            guard receipt.input==normalized,(1...2).contains(receipt.parts.count),receipt.files.count<=receipt.parts.count else { throw LocalMediaURLPolicy.Failure.changed }
            for part in receipt.parts { try LocalMediaURLPolicy.validate(part.url,role:(try? LocalMediaURLPolicy.videoID(normalized)) != nil ? .stream:.direct) }
            for file in receipt.files { try await verify(file,folder:folder) }
            if let merged=receipt.merged { try await verify(merged,folder:folder);progress("Reusing verified retained download and merged source.");return merged }
            progress("Resuming acquisition. Verified completed tracks are reused; partial attempts are kept, never appended.")
        } else {
            let parts:[LocalMediaURLPolicy.Part]
            if let id=try? LocalMediaURLPolicy.videoID(normalized) {
                progress("Requesting the ordinary public YouTube page directly from this iPhone. No login or external converter.")
                let page=try await Transfer.download(normalized,role:.page,folder:folder,ext:"html",maximumBytes:min(4_000_000, try remainingBudget(folder:folder, reserveForMerge:false)),progress:progress)
                parts=try LocalMediaURLPolicy.youtubePlan(Data(contentsOf:folder.appendingPathComponent(page.file)),videoID:id)
            } else { parts=[.init(url:normalized,kind:.combined,ext:normalized.pathExtension.lowercased())] }
            receipt=Receipt(input:normalized,parts:parts,files:[],merged:nil)
            try JSONEncoder().encode(receipt).write(to:receiptURL,options:.atomic)
        }
        var downloaded:Int64=receipt.files.reduce(0){$0+$1.bytes}
        for index in receipt.files.count..<receipt.parts.count {
            try Task.checkCancellation()
            let part=receipt.parts[index]
            progress("Downloading source track \(index+1) of \(receipt.parts.count). Any earlier partial attempt remains retained.")
            let limit=min(try remainingBudget(folder:folder, reserveForMerge:receipt.parts.count == 2, completedSourceBytes:downloaded),LocalMediaURLPolicy.maximumBytes-downloaded)
            guard limit>0 else { throw LocalMediaURLPolicy.Failure.bounds }
            let result=try await Transfer.download(part.url,role:(try? LocalMediaURLPolicy.videoID(normalized)) != nil ? .stream:.direct,folder:folder,ext:part.ext,maximumBytes:limit,progress:progress)
            downloaded += result.bytes
            receipt.files.append(result)
            try JSONEncoder().encode(receipt).write(to:receiptURL,options:.atomic)
        }
        let result:Result
        if receipt.parts.count == 2 {
            guard receipt.parts[0].kind == .video,receipt.parts[1].kind == .audio else { throw LocalMediaURLPolicy.Failure.changed }
            progress("Merging retained audio and video on this iPhone. Original tracks are kept.")
            result=try await merge(video:folder.appendingPathComponent(receipt.files[0].file),audio:folder.appendingPathComponent(receipt.files[1].file),folder:folder,maximumBytes:min(LocalMediaURLPolicy.maximumBytes,try remainingBudget(folder:folder, reserveForMerge:false)),progress:progress)
        } else { result=receipt.files[0] }
        try Task.checkCancellation()
        receipt.merged=result
        try JSONEncoder().encode(receipt).write(to:receiptURL,options:.atomic)
        progress("Acquisition complete: \(result.bytes) verified bytes retained. Starting local media checks.")
        return result
    }
    private static func remainingBudget(folder:URL,reserveForMerge:Bool,completedSourceBytes:Int64 = 0) throws -> Int64 {
        let retained=try retainedBytes(root:folder.deletingLastPathComponent())
        let free=try folder.resourceValues(forKeys:[.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage ?? 0
        return try LocalMediaURLPolicy.byteBudget(retained:retained,free:free,reserveForMerge:reserveForMerge,completedSourceBytes:completedSourceBytes)
    }
    /// Admission must not interpret an unreadable/partial scan as zero retained bytes.
    static func retainedBytes(root:URL) throws -> Int64 {
        try Task.checkCancellation()
        guard root.isFileURL else { throw LocalMediaURLPolicy.Failure.storage }
        let directory=try root.resourceValues(forKeys:[.isDirectoryKey,.isSymbolicLinkKey])
        guard directory.isDirectory==true,directory.isSymbolicLink != true else { throw LocalMediaURLPolicy.Failure.changed }
        var retained:Int64=0
        var scanFailed=false
        guard let entries=FileManager.default.enumerator(at:root,includingPropertiesForKeys:[.fileSizeKey,.isRegularFileKey,.isSymbolicLinkKey],errorHandler:{ _,_ in scanFailed=true;return false }) else { throw LocalMediaURLPolicy.Failure.storage }
        while let url=entries.nextObject() as? URL {
            try Task.checkCancellation()
            let v=try url.resourceValues(forKeys:[.fileSizeKey,.isRegularFileKey,.isSymbolicLinkKey])
            guard v.isSymbolicLink != true else { throw LocalMediaURLPolicy.Failure.changed }
            if v.isRegularFile == true {
                guard let size=v.fileSize,size>=0 else { throw LocalMediaURLPolicy.Failure.storage }
                let (sum,overflow)=retained.addingReportingOverflow(Int64(size))
                guard !overflow else { throw LocalMediaURLPolicy.Failure.storage }
                retained=sum
            }
        }
        guard !scanFailed else { throw LocalMediaURLPolicy.Failure.storage }
        return retained
    }
    static func verify(_ result:Result,folder:URL) async throws {
        guard result.file.range(of:"^[A-Za-z0-9_-]+\\.[a-z0-9]+$",options:.regularExpression) != nil,result.bytes>0,result.bytes<=LocalMediaURLPolicy.maximumBytes else { throw LocalMediaURLPolicy.Failure.changed }
        let checked=try await digest(folder.appendingPathComponent(result.file))
        guard checked.bytes==result.bytes,checked.sha256==result.sha256 else { throw LocalMediaURLPolicy.Failure.changed }
    }
    private static func digest(_ url:URL) async throws -> Result {
        let task=Task.detached { () throws -> Result in
            let v=try url.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
            guard v.isRegularFile==true,v.isSymbolicLink != true,let size=v.fileSize,size>0,size<=LocalMediaURLPolicy.maximumBytes else { throw LocalMediaURLPolicy.Failure.changed }
            let file=try FileHandle(forReadingFrom:url);defer { try? file.close() }
            var hash=SHA256(),count:Int64=0
            while let bytes=try file.read(upToCount:1_048_576),!bytes.isEmpty { try Task.checkCancellation();count += Int64(bytes.count);guard count<=LocalMediaURLPolicy.maximumBytes else { throw LocalMediaURLPolicy.Failure.bounds };hash.update(data:bytes) }
            guard count==size else { throw LocalMediaURLPolicy.Failure.changed }
            return Result(file:url.lastPathComponent,sha256:hash.finalize().map{String(format:"%02x",$0)}.joined(),bytes:count)
        }
        return try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
    }
    static func merge(video:URL,audio:URL,folder:URL,maximumBytes:Int64,progress:@escaping Progress) async throws -> Result {
        let v=AVURLAsset(url:video),a=AVURLAsset(url:audio)
        let vd=try await v.load(.duration),ad=try await a.load(.duration)
        let videos=try await v.loadTracks(withMediaType:.video),audios=try await a.loadTracks(withMediaType:.audio)
        guard vd.seconds.isFinite,ad.seconds.isFinite,(3...1800).contains(vd.seconds),abs(vd.seconds-ad.seconds)<=0.25,
              videos.count==1,audios.count==1,let vt=videos.first,let at=audios.first else { throw LocalMediaURLPolicy.Failure.unsupported }
        let composition=AVMutableComposition()
        guard let cv=composition.addMutableTrack(withMediaType:.video,preferredTrackID:kCMPersistentTrackID_Invalid),let ca=composition.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid) else { throw LocalMediaURLPolicy.Failure.unsupported }
        let duration=CMTimeMinimum(vd,ad)
        try cv.insertTimeRange(CMTimeRange(start:.zero,duration:duration),of:vt,at:.zero)
        try ca.insertTimeRange(CMTimeRange(start:.zero,duration:duration),of:at,at:.zero)
        cv.preferredTransform=try await vt.load(.preferredTransform)
        guard let exporter=AVAssetExportSession(asset:composition,presetName:AVAssetExportPresetPassthrough) else { throw LocalMediaURLPolicy.Failure.unsupported }
        let output=folder.appendingPathComponent("merged-"+UUID().uuidString.lowercased()+".mp4")
        exporter.fileLengthLimit=maximumBytes
        let exportStarted=Date()
        let exportTask=Task { try Task.checkCancellation();try await exporter.export(to:output,as:.mp4) }
        let monitoring=Task {
            var last = -1
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds:1_000_000_000)
                if Task.isCancelled { break }
                let percent=Int(exporter.progress*100)
                if percent != last { last=percent;progress("Merging tracks: \(percent)% reported by the media exporter.") }
            }
        }
        let deadline=Task { try? await Task.sleep(nanoseconds:300_000_000_000);if !Task.isCancelled { exportTask.cancel() } }
        defer { monitoring.cancel();deadline.cancel() }
        do { try await withTaskCancellationHandler { try await exportTask.value } onCancel: { exportTask.cancel() } }
        catch {
            if Task.isCancelled { throw CancellationError() }
            if Date().timeIntervalSince(exportStarted)>=299 { throw LocalMediaURLPolicy.Failure.bounds }
            throw LocalMediaURLPolicy.Failure.response
        }
        try Task.checkCancellation()
        let result=try await digest(output)
        guard result.bytes<=maximumBytes else { throw LocalMediaURLPolicy.Failure.bounds }
        let merged=AVURLAsset(url:output)
        let mergedDuration=try await merged.load(.duration)
        let mergedVideos=try await merged.loadTracks(withMediaType:.video),mergedAudios=try await merged.loadTracks(withMediaType:.audio)
        guard mergedDuration.seconds.isFinite,abs(mergedDuration.seconds-duration.seconds)<=0.1,mergedVideos.count==1,mergedAudios.count==1 else { throw LocalMediaURLPolicy.Failure.response }
        return result
    }

    /// Mutable state is confined to one delegate queue, including cancellation/start races.
    final class Transfer:NSObject,URLSessionDataDelegate,@unchecked Sendable {
        let queue=OperationQueue()
        let role:LocalMediaURLPolicy.Role,folder:URL,ext:String,maximumBytes:Int64,progress:Progress
        let configuration: URLSessionConfiguration
        var session:URLSession?,task:URLSessionDataTask?,continuation:CheckedContinuation<Result,Error>?
        var file:FileHandle?,destination:URL?,hash=SHA256(),count:Int64=0,expected:Int64 = -1
        var canceled=false,done=false,redirects=0,lastProgress=Date.distantPast
        init(role:LocalMediaURLPolicy.Role,folder:URL,ext:String,maximumBytes:Int64,configuration:URLSessionConfiguration,progress:@escaping Progress) {
            self.configuration=configuration
            self.role=role;self.folder=folder;self.ext=ext;self.maximumBytes=maximumBytes;self.progress=progress
            super.init();queue.maxConcurrentOperationCount=1
        }
        static func download(_ url:URL,role:LocalMediaURLPolicy.Role,folder:URL,ext:String,maximumBytes:Int64,configuration:URLSessionConfiguration = .ephemeral,progress:@escaping Progress) async throws -> Result {
            try LocalMediaURLPolicy.validate(url,role:role)
            guard ["html","mp4","mov","m4v","wav","m4a","aac","caf"].contains(ext),maximumBytes>0,maximumBytes<=LocalMediaURLPolicy.maximumBytes else { throw LocalMediaURLPolicy.Failure.bounds }
            let directory=try folder.resourceValues(forKeys:[.isDirectoryKey,.isSymbolicLinkKey])
            guard directory.isDirectory==true,directory.isSymbolicLink != true else { throw LocalMediaURLPolicy.Failure.storage }
            let transfer=Transfer(role:role,folder:folder,ext:ext,maximumBytes:maximumBytes,configuration:configuration,progress:progress)
            return try await withTaskCancellationHandler {
                try Task.checkCancellation()
                return try await withCheckedThrowingContinuation { c in transfer.queue.addOperation { transfer.start(url,c) } }
            } onCancel: { transfer.queue.addOperation { transfer.canceled=true;transfer.finish(.failure(CancellationError())) } }
        }
        private func start(_ url:URL,_ c:CheckedContinuation<Result,Error>) {
            if canceled { c.resume(throwing:CancellationError());return }
            continuation=c
            do {
                let target=folder.appendingPathComponent("download-"+UUID().uuidString.lowercased()+"."+ext)
                guard !FileManager.default.fileExists(atPath:target.path),FileManager.default.createFile(atPath:target.path,contents:nil) else { throw LocalMediaURLPolicy.Failure.storage }
                destination=target;file=try FileHandle(forWritingTo:target)
                configuration.httpCookieStorage = nil;configuration.urlCredentialStorage = nil;configuration.urlCache=nil
                configuration.httpShouldSetCookies=false;configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
                configuration.timeoutIntervalForRequest=30;configuration.timeoutIntervalForResource=900
                session=URLSession(configuration:configuration,delegate:self,delegateQueue:queue)
                var request=URLRequest(url:url);request.setValue("identity",forHTTPHeaderField:"Accept-Encoding")
                request.httpShouldHandleCookies=false
                task=session!.dataTask(with:request);task!.resume()
            } catch { finish(.failure(LocalMediaURLPolicy.Failure.storage)) }
        }
        private func finish(_ result:Swift.Result<Result,Error>) {
            guard !done else { return };done=true
            try? file?.synchronize();try? file?.close();file=nil
            let c=continuation;continuation=nil
            task?.cancel();session?.invalidateAndCancel();session=nil;task=nil
            c?.resume(with:result)
        }
        func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest,completionHandler:@escaping (URLRequest?)->Void) {
            guard !done,!canceled else { completionHandler(nil);return }
            redirects += 1
            guard redirects<=5,let from=response.url,let url=request.url,(try? LocalMediaURLPolicy.validateRedirect(from:from,to:url,role:role)) != nil else { completionHandler(nil);finish(.failure(LocalMediaURLPolicy.Failure.url));return }
            completionHandler(request)
        }
        func urlSession(_ session:URLSession,task:URLSessionTask,didReceive challenge:URLAuthenticationChallenge,completionHandler:@escaping (URLSession.AuthChallengeDisposition,URLCredential?)->Void) {
            guard !done,!canceled else { completionHandler(.cancelAuthenticationChallenge,nil);return }
            if challenge.protectionSpace.authenticationMethod==NSURLAuthenticationMethodServerTrust { completionHandler(.performDefaultHandling,nil) }
            else { completionHandler(.cancelAuthenticationChallenge,nil) }
        }
        func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive response:URLResponse,completionHandler:@escaping (URLSession.ResponseDisposition)->Void) {
            guard !done,!canceled else { completionHandler(.cancel);return }
            guard let http=response as? HTTPURLResponse,http.statusCode==200,
                  let url=response.url,(try? LocalMediaURLPolicy.validate(url,role:role)) != nil,
                  response.expectedContentLength<=maximumBytes else { completionHandler(.cancel);finish(.failure(LocalMediaURLPolicy.Failure.response));return }
            let mime=response.mimeType?.lowercased() ?? ""
            let acceptable=role == .page ? mime=="text/html" : ["video/mp4","video/quicktime","audio/mp4","audio/x-m4a","audio/wav","audio/x-wav","audio/aac","audio/x-caf","application/octet-stream"].contains(mime)
            guard acceptable else { completionHandler(.cancel);finish(.failure(LocalMediaURLPolicy.Failure.unsupported));return }
            expected=response.expectedContentLength;completionHandler(.allow)
        }
        func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive data: Data) {
            guard !done else { return }
            do {
                guard Int64(data.count)<=maximumBytes-count else { throw LocalMediaURLPolicy.Failure.bounds }
                try file?.write(contentsOf:data);hash.update(data:data);count += Int64(data.count)
                if Date().timeIntervalSince(lastProgress)>=1 {
                    lastProgress=Date();try file?.synchronize()
                    let free=try folder.resourceValues(forKeys:[.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage ?? 0
                    guard free>=800_000_000 else { throw LocalMediaURLPolicy.Failure.storage }
                    progress(expected>0 ? "Received \(count) of \(expected) bytes directly from the website." : "Received \(count) bytes; the website has not supplied a total size.")
                }
            } catch { finish(.failure(error is LocalMediaURLPolicy.Failure ? error:LocalMediaURLPolicy.Failure.storage)) }
        }
        func urlSession(_ session:URLSession,task:URLSessionTask,didCompleteWithError error:Error?) {
            guard !done else { return }
            guard error==nil,count>0,expected<0 || count==expected,let destination else { finish(.failure(LocalMediaURLPolicy.Failure.response));return }
            do { try file?.synchronize() } catch { finish(.failure(LocalMediaURLPolicy.Failure.storage));return }
            finish(.success(Result(file:destination.lastPathComponent,sha256:hash.finalize().map{String(format:"%02x",$0)}.joined(),bytes:count)))
        }
    }
}
