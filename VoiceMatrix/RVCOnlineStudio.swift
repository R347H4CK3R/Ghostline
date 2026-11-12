import Foundation
import Combine

/// Owned by the app, not a navigation destination: Back and foreground changes
/// preserve this app session's request. No existing voice library is mutated.
@MainActor final class RVCOnlineStudio: ObservableObject {
    @Published private(set) var catalog: RVCOnlineCatalog?
    @Published var selectedID = ""
    @Published private(set) var input: RVCOnlineImportedAudio?
    @Published private(set) var state = RVCOnlineSession.State.idle
    @Published private(set) var working = false
    @Published private(set) var pausing = false
    @Published private(set) var operationLabel = ""
    @Published private(set) var message = "Choose a laptop model and import a WAV. Audio is sent only when you tap Send audio to laptop."
    @Published private(set) var catalogCheckedAt: Date?
    @Published private(set) var catalogReachable = false
    @Published private(set) var output: URL?
    @Published private(set) var submittedName = ""
    private let makeConnection: () throws -> any RVCOnlineCatalogTransport
    private var connection: (any RVCOnlineCatalogTransport)?
    private var session: RVCOnlineSession?
    private var work: Task<Void, Never>?
    private var generation = UUID()
    private var visible = false
    private var active = true
    private var schedule = RVCOnlineRefreshSchedule()
    private var observation = RVCOnlineObservationLease()
    private var outputAttemptedFor: String?
    private var cancellationCall = false
    var cancellationInFlight: Bool { cancellationCall }

    init(makeConnection: @escaping () throws -> any RVCOnlineCatalogTransport = { try RVCOnlineConnection.paired() }) {
        self.makeConnection = makeConnection
    }
    var pending: Bool { state.requestID != nil && !state.phase.terminal }
    var selected: RVCOnlineModel? { catalog?.models.first { $0.id == selectedID } }
    var canSend: Bool { !working && !pausing && !pending && selected != nil && input != nil && catalog?.onlineConversionAvailable == true && catalogReachable }
    var lastChecked: Date? { state.requestID == nil ? catalogCheckedAt : state.lastSuccessfulCheck }
    var reachable: Bool {
        state.requestID == nil ? catalogReachable : state.connectionError == nil && state.lastSuccessfulCheck != nil
    }
    var stage: String {
        switch state.phase {
        case .idle: return "Ready to prepare a request"
        case .submitting: return "Sending audio to the laptop"
        case .queued: return "Queued on the laptop"
        case .running: return "Converting on the laptop"
        case .waitingForResources: return "Waiting for laptop resources"
        case .downloading: return "Receiving and verifying converted audio"
        case .cancelling:
            return state.receipt?.status == .cancelling ? "Laptop is cancelling" : "Cancellation requested; confirmation pending"
        case .cancelled: return "Laptop confirmed cancellation"
        case .failed: return "Laptop reported conversion failure"
        case .succeeded: return "Converted audio verified"
        case .disconnected: return "Connection interrupted; laptop status unconfirmed"
        case .cancellationUnconfirmed: return "Cancellation not confirmed"
        case .completedBeforeCancellation: return "Laptop finished before cancellation; result not opened"
        }
    }

    func observeWhileVisible() async {
        let observer = observation.begin()
        visible = true
        defer {
            if observation.end(observer) { visible = false; suspend() }
        }
        if active { reconnect() }
        while !Task.isCancelled && observation.owns(observer) {
            if let session {
                let ticket = generation
                let snapshot = await session.current()
                if Task.isCancelled || !observation.owns(observer) { break }
                if generation == ticket, !(state.phase.terminal && state.requestID == snapshot.requestID && !snapshot.phase.terminal) {
                    state = snapshot
                    prepareOutputIfNeeded()
                }
            }
            if schedule.isDue(at: Date(), visible: visible, active: active, pending: pending, busy: working || pausing) {
                refresh()
            }
            do { try await Task.sleep(nanoseconds: 1_000_000_000) } catch { break }
        }
    }
    func setActive(_ value: Bool) {
        active = value
        if !value { suspend() }
        else if visible && !pausing { reconnect() }
    }
    private func suspend() {
        guard !pausing else { return }
        generation = UUID(); work?.cancel(); work = nil; working = false; cancellationCall = false
        catalogReachable = false
        guard let session else { return }
        pausing = true
        Task {
            await session.disconnect()
            state = await session.current()
            pausing = false
            if visible && active { reconnect() }
        }
    }
    func reconnect() {
        guard visible, active, !working, !pausing else { return }
        if pending { refresh(); return }
        refreshCatalog()
    }
    func refreshCatalog() {
        guard visible, active, !working, !pausing, !pending else { return }
        let ticket = begin("Checking laptop models…")
        work = Task {
            defer { finish(ticket) }
            do {
                let next = try makeConnection()
                let catalog = try await next.catalog()
                try Task.checkCancellation()
                guard generation == ticket else { return }
                connection = next
                // Keep a terminal result visible, but use the newly paired origin
                // only for a later explicit submission, never for an active job.
                self.catalog = catalog; catalogCheckedAt = Date(); catalogReachable = true
                if !catalog.models.contains(where: { $0.id == selectedID }) { selectedID = "" }
                message = catalog.onlineConversionAvailable ? "Models are on your laptop. Identity and likeness have not been verified." : "Online RVC is unavailable on this laptop. Offline RVC and RVC text synthesis are not supported."
            } catch {
                guard generation == ticket else { return }
                catalogReachable = false; message = RVCOnlineError.message(for: error)
            }
        }
    }
    func importWAV(_ url: URL) {
        guard !working, !pausing, !pending else { return }
        input = nil
        let ticket = begin("Checking the selected WAV…")
        work = Task {
            defer { finish(ticket) }
            do {
                let imported = try await Task.detached { try RVCOnlineFiles.read(url) }.value
                try Task.checkCancellation()
                guard generation == ticket else { return }
                input = imported; message = "WAV checked. Nothing has been uploaded."
            } catch {
                guard generation == ticket else { return }
                message = "That WAV could not be used. Import mono PCM16 audio between 0.2 and 30 seconds, up to 3 MiB. No audio was sent."
            }
        }
    }
    func importerCancelled() { if input == nil { message = "No WAV selected. Nothing has been uploaded." } }
    func send(audio: AudioStore) {
        guard visible, active, canSend, let selected, let input, let connection else { return }
        do {
            let request = try RVCOnlineConnection.request(model: selected, wav: input.data)
            if audio.playing == output { audio.stop() }
            TemporaryAudio.discard(output); output = nil; outputAttemptedFor = nil
            submittedName = selected.name
            let session = RVCOnlineSession(transport: connection)
            self.session = session
            state = .idle
            run("Sending audio to the laptop…", session: session) { try await session.submit(request) }
        } catch { message = RVCOnlineError.message(for: error) }
    }
    func refresh() {
        guard visible, active, !working, !pausing else { return }
        guard let session, state.requestID != nil else { refreshCatalog(); return }
        if state.phase == .succeeded {
            if output == nil { outputAttemptedFor = nil; prepareOutputIfNeeded() }; return
        }
        run("Checking the laptop request…", session: session) { try await session.refresh() }
    }
    func cancel() {
        guard visible, active, !pausing, !cancellationCall, pending, let session else { return }
        run("Requesting cancellation…", session: session, cancellation: true) { try await session.cancel() }
    }
    /// Explicit only: never retry an upload as a side effect of polling/reconnect.
    func retrySubmission() {
        guard visible, active, !working, !pausing, state.phase == .disconnected, let session else { return }
        run("Retrying the same request ID…", session: session) { try await session.retrySubmission() }
    }
    /// Called only after the view's explicit warning is confirmed. This drops
    /// local tracking, never reports cancellation and never deletes laptop audio.
    func stopTracking() {
        guard pending, !pausing, let previous = session else { return }
        generation = UUID(); let ticket = generation
        work?.cancel(); work = nil; working = false; cancellationCall = false
        session = nil; state = .idle; submittedName = ""; pausing = true
        message = "Stopped checking the old request. It may still be running on the laptop."
        Task {
            await previous.disconnect()
            guard generation == ticket else { return }
            pausing = false
            if visible && active { refreshCatalog() }
        }
    }
    private func begin(_ label: String) -> UUID {
        generation = UUID(); work?.cancel(); working = true; operationLabel = label
        return generation
    }
    private func finish(_ ticket: UUID) {
        guard generation == ticket else { return }
        working = false; work = nil; operationLabel = ""; cancellationCall = false
    }
    private func run(_ label: String, session: RVCOnlineSession, cancellation: Bool = false,
                     operation: @escaping @Sendable () async throws -> RVCOnlineSession.State) {
        let ticket = begin(label)
        cancellationCall = cancellation
        schedule.didAttempt(at: Date())
        work = Task {
            defer { finish(ticket) }
            do {
                let next = try await operation()
                try Task.checkCancellation()
                guard generation == ticket else { return }
                state = next; message = stage; prepareOutputIfNeeded()
            } catch {
                guard generation == ticket else { return }
                state = await session.current()
                guard generation == ticket else { return }
                message = RVCOnlineError.message(for: error)
            }
        }
    }
    private func prepareOutputIfNeeded() {
        guard state.phase == .succeeded, let id = state.requestID, outputAttemptedFor != id,
              let data = state.audio, let result = state.receipt?.result else { return }
        outputAttemptedFor = id
        do { output = try RVCOnlineFiles.verifiedTemporary(data, result: result) }
        catch { message = "Converted audio was verified, but the playback file could not be prepared. Check storage and tap Refresh to retry." }
    }
}
