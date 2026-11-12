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
                    let stale = lastFetched.map { context.date.timeIntervalSince($0) > 10 } ?? true
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
                Text("Refreshes about every 2 seconds while this screen is open and the app is active. Laptop events use laptop timestamps. Device clock differences can affect displayed times.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let snapshot {
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
                Text("No voice names, audio, transcripts or private paths appear in this log. This screen retains only its current snapshot.")
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
                await refresh()
                do { try await Task.sleep(nanoseconds: 2_000_000_000) }
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
                ProgressView(value: video.progress)
                Text("Reported processing progress: \(Int(video.progress * 100))%. This does not confirm completion.").font(.caption)
            }
            Text("Updated \(Date(timeIntervalSince1970: video.updated).formatted(date: .abbreviated, time: .standard)) · \(video.attempts) attempts")
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            if let notice = video.workerHistoryNotice {
                Text(notice).font(.caption).foregroundStyle(.orange)
            }
            if video.workerActive {
                Text("Worker lease was active at this snapshot, until \(Date(timeIntervalSince1970: video.workerLeaseUntil).formatted(date: .abbreviated, time: .standard)). This is not a hardware activity check.").font(.caption)
            } else if video.status == .processing {
                Text("No active worker lease was reported. Processing may be interrupted; check the laptop.").font(.caption).foregroundStyle(.orange)
            }
            if video.status == .retry, video.nextAttempt > 0 {
                Text("Next retry is eligible at \(Date(timeIntervalSince1970: video.nextAttempt).formatted(date: .abbreviated, time: .standard)); worker availability may delay it.").font(.caption)
            }
        }.accessibilityElement(children: .combine)
    }
}
