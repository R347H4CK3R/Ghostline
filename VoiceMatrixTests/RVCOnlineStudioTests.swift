import XCTest
@testable import VoiceMatrix

/// Controller checks use an explicit transport double, not neural inference.
@MainActor final class RVCOnlineStudioTests: XCTestCase {
    private func wait(_ predicate: @MainActor () -> Bool) async throws {
        for _ in 0..<200 {
            if predicate() { return }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTFail("The bounded controller operation did not finish")
    }
    private func sourceWAV() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".wav")
        var data = Data("RIFF".utf8)
        func le(_ value: Int, _ count: Int) { for i in 0..<count { data.append(UInt8((value >> (8 * i)) & 255)) } }
        le(16036, 4); data.append(Data("WAVEfmt ".utf8)); le(16, 4)
        le(1, 2); le(1, 2); le(40000, 4); le(80000, 4); le(2, 2); le(16, 2)
        data.append(Data("data".utf8)); le(16000, 4); data.append(Data(repeating: 1, count: 16000))
        try data.write(to: url); return url
    }
    func testImportNeverUploadsAndRepeatedSendUsesOneRequest() async throws {
        let wire = RVCStudioTransportDouble()
        let model = RVCOnlineStudio(makeConnection: { wire })
        let observation = Task { await model.observeWhileVisible() }
        defer { observation.cancel() }
        try await wait { model.catalog != nil && !model.working }
        let source = try sourceWAV(); defer { try? FileManager.default.removeItem(at: source) }
        model.importWAV(source)
        try await wait { model.input != nil && !model.working }
        let before = await wire.submissions
        XCTAssertEqual(before.count, 0)
        model.selectedID = "test"
        let audio = AudioStore()
        model.send(audio: audio); model.send(audio: audio)
        try await wait { model.state.phase == .queued && !model.working }
        let submitted = await wire.submissions
        XCTAssertEqual(submitted.count, 1)
        XCTAssertEqual(model.state.requestID, submitted[0].requestID)
        observation.cancel(); await observation.value
        try await wait { !model.pausing }
        let cancellations = await wire.cancellations
        XCTAssertEqual(cancellations, 0)
        XCTAssertEqual(model.state.phase, .disconnected)
        let reopened = Task { await model.observeWhileVisible() }
        defer { reopened.cancel() }
        try await wait { model.state.phase == .running && !model.working }
        let afterReconnect = await wire.submissions
        XCTAssertEqual(afterReconnect.count, 1)
        XCTAssertEqual(model.state.requestID, submitted[0].requestID)
        reopened.cancel(); await reopened.value
    }
    func testInvalidImportClearsSelectionWithoutSending() async throws {
        let wire = RVCStudioTransportDouble()
        let model = RVCOnlineStudio(makeConnection: { wire })
        let observation = Task { await model.observeWhileVisible() }
        defer { observation.cancel() }
        try await wait { model.catalog != nil && !model.working }
        let source = try sourceWAV(); defer { try? FileManager.default.removeItem(at: source) }
        model.importWAV(source); try await wait { model.input != nil && !model.working }
        try Data("Not audio".utf8).write(to: source)
        model.importWAV(source); try await wait { !model.working }
        XCTAssertNil(model.input)
        XCTAssertFalse(model.canSend)
        let submitted = await wire.submissions
        XCTAssertTrue(submitted.isEmpty)
        observation.cancel(); await observation.value
    }
}

private actor RVCStudioTransportDouble: RVCOnlineCatalogTransport {
    private(set) var submissions: [RVCOnlineRequest] = []
    private(set) var cancellations = 0
    func catalog() async throws -> RVCOnlineCatalog {
        let model: [String: Any] = ["id": "test", "name": "Test", "categories": ["Private"],
            "modelSHA256": String(repeating: "a", count: 64), "indexSHA256": String(repeating: "b", count: 64),
            "revision": String(repeating: "c", count: 64), "identityVerified": false, "likenessVerified": false]
        return try RVCOnlineCatalog.decode(JSONSerialization.data(withJSONObject: ["schemaVersion": 1,
            "format": "rvc-online-conversion-v1", "onlineConversionAvailable": true,
            "offlineAvailable": false, "textToSpeechAvailable": false, "models": [model]]))
    }
    private func receipt(_ request: RVCOnlineRequest, status: String) throws -> RVCOnlineSnapshot {
        let data = try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "requestID": request.requestID,
            "modelID": request.modelID, "modelSHA256": request.modelSHA256, "indexSHA256": request.indexSHA256,
            "revision": request.revision, "inputSHA256": request.inputSHA256, "status": status,
            "createdAt": 1700000000.0, "updatedAt": 1700000005.0] as [String: Any])
        return try RVCOnlineSnapshot.decode(data, for: request)
    }
    func submit(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        submissions.append(request); return try receipt(request, status: "queued")
    }
    func status(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot { try receipt(request, status: "running") }
    func cancel(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot {
        cancellations += 1; return try receipt(request, status: "cancelled")
    }
    func result(_ request: RVCOnlineRequest, snapshot: RVCOnlineSnapshot) async throws -> Data { throw RVCOnlineError.invalidResponse }
}
