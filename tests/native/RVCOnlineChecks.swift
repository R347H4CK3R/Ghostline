import Foundation

// Hand-written protocol fixtures. Removing any bound/correlation/lifecycle guard
// below must cause a rejection assertion or an explicit state assertion to fail.
@main struct RVCOnlineChecks {
    static let id = "d49dd0a6-16f8-48bb-9d13-123456789abc"
    static let digest = String(repeating: "a", count: 64)
    static var modelObject: [String: Any] { [
        "id": "private_speaker_01", "name": "Private speaker", "categories": ["Private RVC"],
        "modelSHA256": digest, "indexSHA256": String(repeating: "b", count: 64),
        "revision": String(repeating: "c", count: 64), "identityVerified": false, "likenessVerified": false
    ] }
    static func json(_ object: Any) throws -> Data { try JSONSerialization.data(withJSONObject: object) }
    static func check(_ value: Bool) { precondition(value) }
    static func rejects(_ body: () throws -> Void) {
        do { try body(); preconditionFailure("Expected rejection") } catch {}
    }
    static func asyncRejects(_ body: () async throws -> Void) async {
        do { try await body(); preconditionFailure("Expected asynchronous rejection") } catch {}
    }
    static func catalogObject() -> [String: Any] {
        ["schemaVersion": 1, "format": "rvc-online-conversion-v1", "onlineConversionAvailable": true,
         "offlineAvailable": false, "textToSpeechAvailable": false, "models": [modelObject]]
    }
    static func model() throws -> RVCOnlineModel {
        try RVCOnlineCatalog.decode(json(catalogObject())).models[0]
    }
    static func wav(rate: Int = 40000, frames: Int = 8000, channels: Int = 1, bits: Int = 16) -> Data {
        var bytes = Data()
        func literal(_ value: String) { bytes.append(contentsOf: value.utf8) }
        func le(_ value: Int, _ count: Int) { for i in 0..<count { bytes.append(UInt8((value >> (8 * i)) & 255)) } }
        let block = channels * bits / 8, size = frames * block
        literal("RIFF"); le(36 + size, 4); literal("WAVEfmt "); le(16, 4)
        le(1, 2); le(channels, 2); le(rate, 4); le(rate * block, 4); le(block, 2); le(bits, 2)
        literal("data"); le(size, 4); bytes.append(Data(repeating: 1, count: size)); return bytes
    }
    static func request() throws -> RVCOnlineRequest {
        try RVCOnlineRequest(model: model(), wav: wav(), inputSHA256: digest, id: UUID(uuidString: id)!)
    }
    static func receiptObject(_ status: String = "queued", request: RVCOnlineRequest? = nil) throws -> [String: Any] {
        let r = try request ?? self.request()
        return ["schemaVersion": 1, "requestID": r.requestID, "modelID": r.modelID,
                "modelSHA256": r.modelSHA256, "indexSHA256": r.indexSHA256,
                "revision": r.revision, "inputSHA256": r.inputSHA256, "status": status,
                "createdAt": 1700000000.0, "updatedAt": 1700000005.0]
    }
    static func receipt(_ status: String = "queued", request: RVCOnlineRequest? = nil) throws -> RVCOnlineSnapshot {
        let r = try request ?? self.request()
        return try RVCOnlineSnapshot.decode(json(receiptObject(status, request: r)), for: r)
    }
    static func main() async throws {
        let catalog = try RVCOnlineCatalog.decode(json(catalogObject()))
        check(catalog.models.count == 1 && catalog.onlineConversionAvailable)
        check(!catalog.offlineAvailable && !catalog.textToSpeechAvailable)
        var empty = catalogObject(); empty["models"] = []; empty["onlineConversionAvailable"] = false
        check(try RVCOnlineCatalog.decode(json(empty)).models.isEmpty)
        for (key, value) in [("schemaVersion", 2 as Any), ("format", "f5-reference" as Any),
                             ("offlineAvailable", true as Any), ("textToSpeechAvailable", true as Any)] {
            var invalid = catalogObject(); invalid[key] = value
            rejects { _ = try RVCOnlineCatalog.decode(json(invalid)) }
        }
        for (key, value) in [("id", "../model" as Any), ("modelSHA256", digest.uppercased() as Any),
                             ("revision", "changed" as Any), ("name", "Bad\nname" as Any),
                             ("identityVerified", true as Any), ("likenessVerified", true as Any),
                             ("categories", [] as Any)] {
            var bad = modelObject; bad[key] = value
            var invalid = catalogObject(); invalid["models"] = [bad]
            rejects { _ = try RVCOnlineCatalog.decode(json(invalid)) }
        }
        var bounded = catalogObject()
        let maximumModels = (0..<64).map { index -> [String: Any] in
            var entry = modelObject; entry["id"] = "private_" + String(index); return entry
        }
        bounded["models"] = maximumModels
        check(try RVCOnlineCatalog.decode(json(bounded)).models.count == 64)
        var extraModel = modelObject; extraModel["id"] = "private_64"
        bounded["models"] = maximumModels + [extraModel]
        rejects { _ = try RVCOnlineCatalog.decode(json(bounded)) }
        var duplicate = catalogObject(); duplicate["models"] = [modelObject, modelObject]
        rejects { _ = try RVCOnlineCatalog.decode(json(duplicate)) }
        rejects { _ = try RVCOnlineCatalog.decode(Data(repeating: 32, count: 1_048_577)) }
        for audio in [wav(frames: 7999), wav(frames: 1_200_001), wav(channels: 2), wav(bits: 8),
                      wav(rate: 8000), Data(wav().dropLast()), Data(repeating: 0, count: 3_145_729)] {
            rejects { _ = try RVCOnlineWAV.inspect(audio) }
        }
        var silent = wav()
        silent.replaceSubrange(44..<silent.count, with: Data(repeating: 0, count: silent.count - 44))
        rejects { _ = try RVCOnlineWAV.inspect(silent) }
        var clipped = wav(); clipped[44] = 255; clipped[45] = 127
        rejects { _ = try RVCOnlineWAV.inspect(clipped) }
        let audio = try RVCOnlineWAV.inspect(wav())
        check(audio.sampleRate == 40000 && audio.seconds == 0.2)
        var trailing = wav(); trailing.append(0)
        rejects { _ = try RVCOnlineWAV.inspect(trailing) }
        var wrongRate = wav(); wrongRate[28] = 0
        rejects { _ = try RVCOnlineWAV.inspect(wrongRate) }
        // A maximum-size slash-rich WAV must fit the server's JSON cap. The
        // fixture includes legal RIFF metadata padding and 30 seconds at 48 kHz.
        var maximumWAV = wav(rate: 48000, frames: 1_440_000)
        maximumWAV.replaceSubrange(44..<maximumWAV.count, with: Data(repeating: 254, count: maximumWAV.count - 44))
        let chunkBytes = 3_145_728 - maximumWAV.count - 8
        maximumWAV.append(Data("JUNK".utf8))
        for i in 0..<4 { maximumWAV.append(UInt8((chunkBytes >> (i * 8)) & 255)) }
        maximumWAV.append(Data(repeating: 255, count: chunkBytes))
        let riffBytes = maximumWAV.count - 8
        for i in 0..<4 { maximumWAV[4 + i] = UInt8((riffBytes >> (i * 8)) & 255) }
        check(maximumWAV.count == 3_145_728)
        let maximumRequest = try RVCOnlineRequest(model: model(), wav: maximumWAV, inputSHA256: digest)
        let maximumBody = try maximumRequest.encodedBody()
        check(maximumBody.count <= 4_198_400)
        let maximumJSON = try JSONSerialization.jsonObject(with: maximumBody) as! [String: Any]
        check(Data(base64Encoded: maximumJSON["wavBase64"] as! String) == maximumWAV)
        var oversizedWAV = maximumWAV; oversizedWAV.append(0)
        rejects { _ = try RVCOnlineRequest(model: model(), wav: oversizedWAV, inputSHA256: digest) }
        let request = try self.request()
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as! [String: Any]
        check(encoded["requestID"] as? String == id && encoded["wavBase64"] as? String == wav().base64EncodedString())
        for status in ["queued", "running", "waiting-for-resources", "cancelling", "cancelled", "failed"] {
            check(try receipt(status).status.rawValue == status)
        }
        for (key, value) in [("schemaVersion", 2 as Any), ("requestID", id.uppercased() as Any),
                             ("requestID", UUID().uuidString.lowercased() as Any), ("modelID", "another" as Any),
                             ("inputSHA256", String(repeating: "d", count: 64) as Any),
                             ("modelSHA256", String(repeating: "d", count: 64) as Any),
                             ("indexSHA256", String(repeating: "d", count: 64) as Any),
                             ("revision", String(repeating: "d", count: 64) as Any),
                             ("status", "done" as Any)] {
            var invalid = try receiptObject(); invalid[key] = value
            rejects { _ = try RVCOnlineSnapshot.decode(json(invalid), for: request) }
        }
        let timed = try receipt()
        check(timed.createdAt == 1700000000 && timed.updatedAt == 1700000005)
        for key in ["createdAt", "updatedAt"] {
            var missing = try receiptObject(); missing.removeValue(forKey: key)
            rejects { _ = try RVCOnlineSnapshot.decode(json(missing), for: request) }
            for bad in [-1.0 as Any, "yesterday" as Any, true as Any] {
                var invalid = try receiptObject(); invalid[key] = bad
                rejects { _ = try RVCOnlineSnapshot.decode(json(invalid), for: request) }
            }
            let original = String(data: try json(receiptObject()), encoding: .utf8)!
            let overflow = original.replacingOccurrences(of: "\"" + key + "\":170000000", with: "\"" + key + "\":1e999000000")
            rejects { _ = try RVCOnlineSnapshot.decode(Data(overflow.utf8), for: request) }
        }
        let now = Date(timeIntervalSince1970: 1700000100)
        let privateError = NSError(domain: "private", code: 1, userInfo: [NSLocalizedDescriptionKey: "https://user:secret@host/private?token=hidden"])
        check(RVCOnlineError.message(for: privateError) == "The laptop connection could not be verified. Check pairing and try again.")
        check(RVCOnlineError.message(for: RVCOnlineError.authenticationRequired) == RVCOnlineError.authenticationRequired.errorDescription)

        var ownership = RVCOnlineObservationLease()
        let firstObserver = ownership.begin()
        check(ownership.owns(firstObserver))
        let currentObserver = ownership.begin()
        check(!ownership.owns(firstObserver))
        check(!ownership.end(firstObserver))
        check(ownership.owns(currentObserver))
        check(ownership.end(currentObserver))
        check(!ownership.owns(currentObserver))
        check(!ownership.end(currentObserver))

        var schedule = RVCOnlineRefreshSchedule()
        check(schedule.isDue(at: now, visible: true, active: true, pending: true, busy: false))
        schedule.didAttempt(at: now)
        check(!schedule.isDue(at: now.addingTimeInterval(29), visible: true, active: true, pending: true, busy: false))
        check(schedule.isDue(at: now.addingTimeInterval(30), visible: true, active: true, pending: true, busy: false))
        check(!schedule.isDue(at: now.addingTimeInterval(30), visible: false, active: true, pending: true, busy: false))
        check(!schedule.isDue(at: now.addingTimeInterval(30), visible: true, active: false, pending: true, busy: false))
        check(!schedule.isDue(at: now.addingTimeInterval(30), visible: true, active: true, pending: true, busy: true))
        check(!schedule.isDue(at: now.addingTimeInterval(30), visible: true, active: true, pending: false, busy: false))
        check(RVCOnlineRefreshSchedule.freshness(checkedAt: now, now: now.addingTimeInterval(59), reachable: true) == .recent)
        check(RVCOnlineRefreshSchedule.freshness(checkedAt: now, now: now.addingTimeInterval(60), reachable: true) == .stale)
        check(RVCOnlineRefreshSchedule.freshness(checkedAt: now, now: now, reachable: false) == .disconnected)
        check(RVCOnlineRefreshSchedule.freshness(checkedAt: nil, now: now, reachable: true) == .neverChecked)
        try sharedWAVChecks()
        rejects { _ = try receipt("succeeded") }
        var result = try receiptObject("succeeded")
        result["result"] = ["sha256": digest, "bytes": 16044, "sampleRate": 40000, "seconds": 0.2]
        check(try RVCOnlineSnapshot.decode(json(result), for: request).result?.bytes == 16044)
        for (key, value) in [("bytes", 3_145_729 as Any), ("sampleRate", 48000 as Any), ("seconds", 31 as Any), ("sha256", "bad" as Any)] {
            var invalid = result, metadata = result["result"] as! [String: Any]; metadata[key] = value; invalid["result"] = metadata
            rejects { _ = try RVCOnlineSnapshot.decode(json(invalid), for: request) }
        }
        var premature = result; premature["status"] = "running"
        rejects { _ = try RVCOnlineSnapshot.decode(json(premature), for: request) }
        for root in ["http://laptop.test", "https://u:p@laptop.test", "https://laptop.test/path", "https://laptop.test/?q=x", "https://laptop.test/#x"] {
            rejects { _ = try RVCOnlineEndpoint(root: URL(string: root)!) }
        }
        let endpoint = try RVCOnlineEndpoint(root: URL(string: "https://laptop.test/")!)
        check(try endpoint.job(id).absoluteString == "https://laptop.test/rvc/conversions/" + id)
        rejects { _ = try endpoint.job("../../private") }
        try await lifecycleChecks(request)
        print("RVC online checks passed: strict catalog/receipts, pinned jobs, bounded PCM WAV, cancellation, reconnect and stale responses")
    }
    static func sharedWAVChecks() throws {
        guard CommandLine.arguments.count == 2 else { preconditionFailure("Pass the shared WAV fixture directory") }
        let folder = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let manifest = try JSONDecoder().decode([String: Bool].self, from: Data(contentsOf: folder.appendingPathComponent("manifest.json")))
        for (name, valid) in manifest {
            let bytes = try Data(contentsOf: folder.appendingPathComponent(name))
            if valid { _ = try RVCOnlineWAV.inspect(bytes) }
            else { rejects { _ = try RVCOnlineWAV.inspect(bytes) } }
        }
    }
    static func lifecycleChecks(_ request: RVCOnlineRequest) async throws {
        let wire = ControlledRVCTransport()
        let checked = Date(timeIntervalSince1970: 1700000200)
        let session = RVCOnlineSession(transport: wire, now: { checked })
        let pending = Task { try await session.submit(request) }
        await wire.waitUntilSubmitting()
        await session.disconnect()
        await wire.finishSubmit(try receipt())
        await asyncRejects { _ = try await pending.value }
        check(await session.current().phase == .disconnected)
        let retried = Task { try await session.retrySubmission() }
        await wire.waitUntilSubmitting()
        await wire.finishSubmit(try receipt())
        check(try await retried.value.requestID == request.requestID)
        await wire.setStatus(try receipt("running"))
        check(try await session.refresh().phase == .running)
        check(await session.current().lastSuccessfulCheck == checked)
        await wire.setCancelFailure(true)
        await asyncRejects { _ = try await session.cancel() }
        check(await session.current().phase == .cancellationUnconfirmed)
        check(await session.current().lastSuccessfulCheck == checked)
        await wire.setStatus(try receipt("cancelled"))
        check(try await session.refresh().phase == .cancelled)

        let second = Task { try await session.submit(request) }
        await wire.waitUntilSubmitting()
        await wire.finishSubmit(try receipt())
        _ = try await second.value
        await asyncRejects { _ = try await session.submit(request) }
        await wire.setCancelFailure(false)
        await wire.setStatus(try receipt("cancelling"))
        check(try await session.cancel().phase == .cancelling)
        var success = try receiptObject("succeeded")
        success["result"] = ["sha256": digest, "bytes": 16044, "sampleRate": 40000, "seconds": 0.2]
        await wire.setStatus(try RVCOnlineSnapshot.decode(json(success), for: request))
        let state = try await session.refresh()
        check(state.phase == .completedBeforeCancellation && state.audio == nil)
        check(await wire.resultCalls == 0)
        await asyncRejects { _ = try await session.retrySubmission() }

        let normalWire = ControlledRVCTransport()
        let normal = RVCOnlineSession(transport: normalWire)
        let start = Task { try await normal.submit(request) }
        await normalWire.waitUntilSubmitting(); await normalWire.finishSubmit(try receipt())
        _ = try await start.value
        await normalWire.setStatus(try RVCOnlineSnapshot.decode(json(success), for: request))
        let ready = try await normal.refresh()
        check(ready.phase == .succeeded && ready.audio == wav())
        _ = try await normal.refresh()
        check(await normalWire.resultCalls == 1)
        await normal.disconnect()
        check(await normal.current().phase == .succeeded)

        let delayedWire = ControlledRVCTransport()
        let delayed = RVCOnlineSession(transport: delayedWire)
        let upload = Task { try await delayed.submit(request) }
        await delayedWire.waitUntilSubmitting(); await delayedWire.finishSubmit(try receipt())
        _ = try await upload.value
        await delayedWire.setStatus(try RVCOnlineSnapshot.decode(json(success), for: request))
        await delayedWire.holdResult()
        let download = Task { try await delayed.refresh() }
        await delayedWire.waitUntilDownloading()
        check(await delayed.current().phase == .downloading)
        check(await delayed.current().lastSuccessfulCheck != nil)
        await delayedWire.setStatus(try receipt("cancelling"))
        check(try await delayed.cancel().phase == .cancelling)
        await delayedWire.finishResult()
        await asyncRejects { _ = try await download.value }
        check(await delayed.current().phase == .cancelling)
        check(await delayed.current().audio == nil)
    }
}

actor ControlledRVCTransport: RVCOnlineTransport {
    private var submitContinuation: CheckedContinuation<RVCOnlineSnapshot, Error>?
    private var submittedWaiter: CheckedContinuation<Void, Never>?
    private var snapshot: RVCOnlineSnapshot?
    private var failCancel = false
    private var resultHeld = false
    private var resultContinuation: CheckedContinuation<Data, Error>?
    private var downloadWaiter: CheckedContinuation<Void, Never>?
    private(set) var resultCalls = 0
    func submit(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        try await withCheckedThrowingContinuation { continuation in
            submitContinuation = continuation; submittedWaiter?.resume(); submittedWaiter = nil
        }
    }
    func waitUntilSubmitting() async {
        if submitContinuation != nil { return }
        await withCheckedContinuation { submittedWaiter = $0 }
    }
    func finishSubmit(_ value: RVCOnlineSnapshot) {
        let continuation = submitContinuation; submitContinuation = nil; continuation?.resume(returning: value)
    }
    func setStatus(_ value: RVCOnlineSnapshot) { snapshot = value }
    func setCancelFailure(_ value: Bool) { failCancel = value }
    func status(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot { snapshot! }
    func cancel(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        if failCancel { throw URLError(.notConnectedToInternet) }; return snapshot!
    }
    func result(_ request: RVCOnlineRequest, snapshot: RVCOnlineSnapshot) async throws -> Data {
        resultCalls += 1
        if resultHeld {
            return try await withCheckedThrowingContinuation { continuation in
                resultContinuation = continuation; downloadWaiter?.resume(); downloadWaiter = nil
            }
        }
        return RVCOnlineChecks.wav()
    }
    func holdResult() { resultHeld = true }
    func waitUntilDownloading() async {
        if resultContinuation != nil { return }
        await withCheckedContinuation { downloadWaiter = $0 }
    }
    func finishResult() {
        let continuation = resultContinuation; resultContinuation = nil
        continuation?.resume(returning: RVCOnlineChecks.wav())
    }
}
