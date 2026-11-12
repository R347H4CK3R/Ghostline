import Foundation

protocol RVCOnlineTransport: Sendable {
    func submit(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot
    func status(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot
    func cancel(_ request: RVCOnlineRequest) async throws -> RVCOnlineSnapshot
    func result(_ request: RVCOnlineRequest, snapshot: RVCOnlineSnapshot) async throws -> Data
}
protocol RVCOnlineCatalogTransport: RVCOnlineTransport {
    func catalog() async throws -> RVCOnlineCatalog
}

/// Keeps one immutable laptop job through local interruption. Disconnect stops
/// local work, not the laptop. A successful status check has its own local time;
/// it never replaces the server's last-activity timestamp or invents progress.
actor RVCOnlineSession {
    enum Phase: Sendable, Equatable {
        case idle, submitting, queued, running, waitingForResources, downloading, cancelling
        case cancelled, failed, succeeded, disconnected, cancellationUnconfirmed, completedBeforeCancellation
        var terminal: Bool {
            self == .cancelled || self == .failed || self == .succeeded || self == .completedBeforeCancellation
        }
    }
    struct State: Sendable {
        let phase: Phase
        let requestID: String?
        let receipt: RVCOnlineSnapshot?
        let audio: Data?
        let connectionError: String?
        let lastSuccessfulCheck: Date?
        static let idle = State(phase: .idle, requestID: nil, receipt: nil, audio: nil,
                                connectionError: nil, lastSuccessfulCheck: nil)
    }
    private struct Update: Sendable { let receipt: RVCOnlineSnapshot; let audio: Data? }
    private let transport: any RVCOnlineTransport
    private let now: @Sendable () -> Date
    private var request: RVCOnlineRequest?
    private var generation: UInt64 = 0
    private var operation: Task<Update, Error>?
    private var cancellationRequested = false
    private var state = State.idle

    init(transport: any RVCOnlineTransport, now: @escaping @Sendable () -> Date = { Date() }) {
        self.transport = transport; self.now = now
    }
    func current() -> State { state }

    func submit(_ request: RVCOnlineRequest) async throws -> State {
        guard self.request == nil || state.phase.terminal else { throw RVCOnlineError.busy }
        self.request = request; cancellationRequested = false
        return try await send(request)
    }
    func retrySubmission() async throws -> State {
        guard let request else { throw RVCOnlineError.noRequest }
        guard state.phase == .disconnected, operation == nil, !cancellationRequested else { throw RVCOnlineError.busy }
        return try await send(request)
    }
    private func send(_ request: RVCOnlineRequest) async throws -> State {
        state = State(phase: .submitting, requestID: request.requestID, receipt: nil, audio: nil,
                      connectionError: nil, lastSuccessfulCheck: nil)
        let wire = transport
        return try await run(request, downloadResult: true) { try await wire.submit(request) }
    }
    func refresh() async throws -> State {
        guard let request else { throw RVCOnlineError.noRequest }
        guard operation == nil else { throw RVCOnlineError.busy }
        if state.phase.terminal { return state }
        let wire = transport
        return try await run(request, downloadResult: !cancellationRequested) { try await wire.status(request) }
    }
    func cancel() async throws -> State {
        guard let request else { throw RVCOnlineError.noRequest }
        if state.phase.terminal { return state }
        cancellationRequested = true
        state = State(phase: .cancelling, requestID: request.requestID, receipt: state.receipt, audio: nil,
                      connectionError: nil, lastSuccessfulCheck: state.lastSuccessfulCheck)
        let wire = transport
        return try await run(request, downloadResult: false) { try await wire.cancel(request) }
    }
    func disconnect() {
        generation &+= 1; operation?.cancel(); operation = nil
        guard let request, !state.phase.terminal else { return }
        state = State(phase: cancellationRequested ? .cancellationUnconfirmed : .disconnected,
                      requestID: request.requestID, receipt: state.receipt, audio: nil,
                      connectionError: "Disconnected. The laptop may still be processing this request. Reconnect to check or cancel it.",
                      lastSuccessfulCheck: state.lastSuccessfulCheck)
    }
    private func phase(for status: RVCOnlineStatus) -> Phase {
        switch status {
        case .queued: return cancellationRequested ? .cancelling : .queued
        case .running: return cancellationRequested ? .cancelling : .running
        case .waitingForResources: return cancellationRequested ? .cancelling : .waitingForResources
        case .cancelling: return .cancelling
        case .cancelled: return .cancelled
        case .failed: return .failed
        case .succeeded: return cancellationRequested ? .completedBeforeCancellation : .succeeded
        }
    }
    private func received(_ receipt: RVCOnlineSnapshot, request: RVCOnlineRequest,
                          generation expected: UInt64, downloading: Bool) throws {
        try Task.checkCancellation()
        guard generation == expected else { throw CancellationError() }
        try receipt.validate(for: request)
        state = State(phase: downloading ? .downloading : phase(for: receipt.status), requestID: request.requestID,
                      receipt: receipt, audio: nil, connectionError: nil, lastSuccessfulCheck: now())
    }
    private func run(_ request: RVCOnlineRequest, downloadResult: Bool,
                     work: @escaping @Sendable () async throws -> RVCOnlineSnapshot) async throws -> State {
        generation &+= 1
        let expected = generation
        operation?.cancel()
        let task = Task {
            try Task.checkCancellation()
            let receipt = try await work()
            let downloading = downloadResult && receipt.status == .succeeded
            try self.received(receipt, request: request, generation: expected, downloading: downloading)
            var audio: Data?
            if downloading { audio = try await self.transport.result(request, snapshot: receipt) }
            return Update(receipt: receipt, audio: audio)
        }
        operation = task
        do {
            let update = try await withTaskCancellationHandler(operation: { try await task.value }, onCancel: { task.cancel() })
            try Task.checkCancellation()
            guard generation == expected else { throw CancellationError() }
            operation = nil
            state = State(phase: phase(for: update.receipt.status), requestID: request.requestID,
                          receipt: update.receipt, audio: cancellationRequested ? nil : update.audio,
                          connectionError: nil, lastSuccessfulCheck: state.lastSuccessfulCheck)
            return state
        } catch {
            guard generation == expected else { throw CancellationError() }
            operation = nil
            state = State(phase: cancellationRequested ? .cancellationUnconfirmed : .disconnected,
                          requestID: request.requestID, receipt: state.receipt, audio: nil,
                          connectionError: "The connection ended before this request could be confirmed. Reconnect to check the same request.",
                          lastSuccessfulCheck: state.lastSuccessfulCheck)
            throw error
        }
    }
}
