import SwiftUI

struct VideoWorkflowView: View {
    let videoID: String?
    @Environment(\.scenePhase) private var scenePhase
    @State private var snapshot: VideoWorkflowSnapshot?
    @State private var lastFetched: Date?
    @State private var unavailable = false
    @State private var refreshing = false
    @State private var visible = false
    @State private var refreshID = UUID()
    @State private var requestGate = VideoWorkflowRequestGate()

    private struct PollID: Hashable { let active: Bool; let revision: UUID }

    init(videoID: String? = nil) { self.videoID = videoID }

    @MainActor private func refresh() async {
        guard visible, scenePhase == .active, !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        do {
            let identifier = videoID
            guard let received = try await requestGate.fetch({ try await LaptopConnection.workflow(videoID: identifier) }) else { return }
            try Task.checkCancellation()
            guard visible, scenePhase == .active else { return }
            snapshot = received
            lastFetched = Date()
            unavailable = false
        } catch {
            if !Task.isCancelled { unavailable = true }
        }
    }

    var body: some View {
        List {
            Section("Laptop connection") {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    let stale = VideoWorkflowFreshness.isStale(lastFetched: lastFetched?.timeIntervalSince1970, now: context.date.timeIntervalSince1970)
                    if scenePhase != .active {
                        Label("Updates paused while this screen is inactive", systemImage: "pause.circle")
                    } else if unavailable {
                        Label("Live workflow unavailable", systemImage: "wifi.slash").foregroundStyle(.orange)
                        Text("The laptop may be offline or this companion may not support workflow logs. Check the connection and pairing. Saved voices remain available offline.").font(.caption)
                    } else if snapshot == nil {
                        Text("Waiting for a verified laptop response…")
                    } else if stale {
                        Label("Snapshot is stale. Waiting for a fresh response…", systemImage: "clock.badge.exclamationmark")
                    } else {
                        Label("Laptop snapshot received", systemImage: "checkmark.circle")
                    }
                    if let snapshot {
                        Text("Laptop snapshot: \(Date(timeIntervalSince1970: snapshot.observedAt).formatted(date: .abbreviated, time: .standard))")
                            .font(.caption.monospacedDigit())
                    }
                    if let lastFetched {
                        Text("Last refreshed \(lastFetched.formatted(date: .abbreviated, time: .standard)). \(unavailable || stale ? "Showing the last known snapshot, not live progress." : "Waiting alone is not proof of progress.")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if refreshing { ProgressView("Refreshing workflow…") }
                Text("Refreshes about every 30 seconds while this screen is open and the app is active. Laptop events use laptop timestamps. Device clock differences can affect displayed times.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let snapshot {
                if let catalog = snapshot.catalog { WorkflowVoiceCatalogView(catalog: catalog) }
                else { Text("Update the laptop companion to include voice-list observations in this log.").font(.caption).foregroundStyle(.secondary) }
                if snapshot.videos.isEmpty {
                    Section("Video requests") {
                        Text(videoID == nil ? "No video requests were returned by the laptop." : "The laptop has no workflow snapshot for this video.")
                        Text("An empty history does not prove the phone list was received. Check the sending log on Video List.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                ForEach(snapshot.videos) { video in
                    Section("Video \(video.id)") {
                        VideoWorkflowSummary(video: video)
                        DisclosureGroup("Recorded laptop events · \(video.events.count)") {
                            if video.events.isEmpty { Text("No retained events. The status above is the current snapshot only.").font(.caption) }
                            ForEach(video.events.reversed()) { event in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(event.message)
                                    Text("\(Date(timeIntervalSince1970: event.time).formatted(date: .abbreviated, time: .standard)) · Laptop · Attempt \(event.attempt)")
                                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                                    if event.total > 0 { Text("\(event.completed) of \(event.total) reported").font(.caption) }
                                }.accessibilityElement(children: .combine)
                            }
                        }
                        if videoID == nil {
                            NavigationLink("More history for this video") { VideoWorkflowView(videoID: video.id) }
                        }
                        Text(video.historyNotice).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if snapshot.hasMore == true {
                    Text("Showing at most 200 laptop requests. Open a video's workflow from Video List if it is missing here.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("Phone saving is separate") {
                Text("Listening review is not completion. Sending a collection from the laptop does not mean it was saved on this iPhone.")
                Text("Open Voices → Live sync log for the separate transfer, phone validation and offline saving steps. This workflow view does not start a sync.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Safe voice-list names appear only in the catalog section. No audio, transcripts, credentials or private paths appear in this log. This screen retains only its current snapshot.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Video workflow")
        .toolbar {
            Button("Refresh") { refreshID = UUID() }.disabled(refreshing || scenePhase != .active)
        }
        .task(id: PollID(active: visible && scenePhase == .active, revision: refreshID)) {
            guard visible, scenePhase == .active else { return }
            while !Task.isCancelled {
                let nextRefresh = ContinuousClock.now.advanced(by: .nanoseconds(Int64(VideoWorkflowFreshness.refreshNanoseconds)))
                await refresh()
                do { try await Task.sleep(until: nextRefresh, clock: .continuous) }
                catch { return }
            }
        }
        .onAppear { visible = true }
        .onDisappear { visible = false }
        .accessibilityIdentifier("video-workflow-log")
    }
}

private struct VideoWorkflowSummary: View {
    let video: VideoWorkflowVideo
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(video.status.title).font(.headline)
            Text("Current laptop status, not inferred from events").font(.caption).foregroundStyle(.secondary)
            if video.status == .processing {
                Text("Processing is active in the queue. Stage duration is not a completion percentage.").font(.caption)
            }
            if let stage = video.lastRecordedStage {
                Text("\(video.status == .processing ? "Current reported stage" : "Last recorded stage"): \(stage.message)")
            }
            TimelineView(.periodic(from: .now, by: 1)) { context in
                if let at = video.lastRecordedStageAt {
                    Text("Last stage event: \(Date(timeIntervalSince1970: at).formatted(date: .abbreviated, time: .standard)) · \(max(0, Int(context.date.timeIntervalSince1970 - at))) seconds ago")
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
                if let at = video.lastEventAt ?? video.events.last?.time {
                    Text("Last recorded event: \(Date(timeIntervalSince1970: at).formatted(date: .abbreviated, time: .standard))")
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            Text("Queue / heartbeat update \(Date(timeIntervalSince1970: video.updated).formatted(date: .abbreviated, time: .standard)) · \(video.attempts) attempts")
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            if let notice = video.workerHistoryNotice {
                Text(notice).font(.caption).foregroundStyle(.orange)
            }
            if video.workerActive {
                Text("Worker lease was active at this snapshot, until \(Date(timeIntervalSince1970: video.workerLeaseUntil).formatted(date: .abbreviated, time: .standard)). This reports worker responsiveness, not compute progress. Long computation alone does not prove a stall.").font(.caption)
            } else if video.status == .processing {
                Text("No active worker lease was reported at this snapshot. Worker responsiveness is unconfirmed; check the laptop. This alone does not establish why processing stopped reporting.").font(.caption).foregroundStyle(.orange)
            }
            if video.status == .retry, video.nextAttempt > 0 {
                Text("Next retry is eligible at \(Date(timeIntervalSince1970: video.nextAttempt).formatted(date: .abbreviated, time: .standard)); worker availability may delay it.").font(.caption)
            }
        }.accessibilityElement(children: .combine)
    }
}


private struct WorkflowVoiceCatalogView: View {
    let catalog: WorkflowVoiceCatalog
    var body: some View {
        Section("Laptop voice list · \(catalog.count)") {
            if catalog.state == .checking { Text("Checking the existing laptop collection…") }
            if catalog.state == .notChecked { Text("No verified voice-list observation yet.") }
            if catalog.state == .unavailable {
                Text("Voice-list check failed. Showing the last verified list; existing voices were kept.")
                    .foregroundStyle(.orange)
            }
            if let checked = catalog.checkedAt {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    Text("List checked \(Date(timeIntervalSince1970: checked).formatted(date: .abbreviated, time: .standard))")
                        .font(.caption.monospacedDigit())
                    if context.date.timeIntervalSince1970 - checked > 75 {
                        Text("Catalog observation is stale. The displayed list may have changed.")
                            .font(.caption).foregroundStyle(.orange)
                    }
                }
            }
            DisclosureGroup("Voices currently observed · \(catalog.count)") {
                ForEach(catalog.voices.sorted { $0.displayName.localizedStandardCompare($1.displayName) == .orderedAscending }) { voice in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(voice.displayName)
                        Text("First observed \(Date(timeIntervalSince1970: voice.firstObservedAt).formatted(date: .abbreviated, time: .standard))")
                            .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
            DisclosureGroup("Voice-list changes · \(catalog.events.count)") {
                ForEach(catalog.events.sorted { $0.sequence > $1.sequence }) { event in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(event.message)
                        Text(Date(timeIntervalSince1970: event.time).formatted(date: .abbreviated, time: .standard))
                            .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
            Text("Times show when the laptop observed a list or change, not exact creation times. Up to 160 recent observations are kept until the companion restarts. A first observation is not a newly created voice. This does not download, replace or delete any saved voices.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
