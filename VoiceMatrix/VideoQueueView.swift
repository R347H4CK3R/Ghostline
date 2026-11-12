import SwiftUI
import UniformTypeIdentifiers

private struct QueuedVideo: Codable, Identifiable {
    let id: String
    var name: String
    let url: String
}

struct VideoQueueView: View {
    @AppStorage("videoQueue.v1") private var saved = Data()
    @State private var videos: [QueuedVideo] = []
    @State private var name = ""
    @State private var link = ""
    @State private var message = ""
    @State private var exported: URL?
    @State private var sending = false
    @State private var submissions = VideoWorkflowSubmissionLog()
    @State private var manualSend: Task<Void, Never>?

    private func persist() {
        do {
            saved = try JSONEncoder().encode(videos)
            exported = nil
        } catch { message = "Your list could not be saved. Please try again." }
    }
    private func add() {
        guard let parts = URLComponents(string: link.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme == "https", parts.user == nil, parts.password == nil else {
            message = "Paste a full HTTPS YouTube video link."; return
        }
        let path = parts.path.split(separator: "/").map(String.init)
        let identifier: String?
        switch parts.host?.lowercased() {
        case "youtu.be": identifier = path.count == 1 ? path.first : nil
        case "youtube.com", "www.youtube.com", "m.youtube.com":
            if parts.path == "/watch" { identifier = parts.queryItems?.first(where: { $0.name == "v" })?.value }
            else if path.count == 2 && ["live", "shorts", "embed"].contains(path[0]) { identifier = path[1] }
            else { identifier = nil }
        default: identifier = nil
        }
        guard let identifier, identifier.range(of: "^[A-Za-z0-9_-]{11}$", options: .regularExpression) != nil else {
            message = "That link does not identify a supported YouTube video."; return
        }
        guard !videos.contains(where: { $0.id == identifier }) else { message = "That video is already on your list."; return }
        let cleanName = name.replacingOccurrences(of: "\n", with: " ").replacingOccurrences(of: "\r", with: " ").replacingOccurrences(of: "\t", with: " ")
        videos.append(QueuedVideo(id: identifier, name: cleanName, url: "https://www.youtube.com/watch?v=" + identifier))
        persist(); link = ""; name = ""; message = "Added to your list."
    }
    private func exportList() {
        do {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent("VoiceMatrixQueue", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let destination = directory.appendingPathComponent("VoiceMatrix-video-queue.txt")
            let text = videos.map { $0.name + "\t" + $0.url }.joined(separator: "\n") + "\n"
            try text.write(to: destination, atomically: true, encoding: .utf8)
            exported = destination; message = "Your current list is ready to share."
        } catch { message = "The list could not be exported. Please try again." }
    }
    @MainActor private func sendList(_ pending: [QueuedVideo]) async {
        guard !sending, !pending.isEmpty, !Task.isCancelled else { return }
        sending = true
        let attempt = submissions.begin(count: pending.count)
        defer { sending = false }
        do {
            let data = try JSONEncoder().encode(["videos": pending])
            let accepted = try await LaptopConnection.send(data)
            try Task.checkCancellation()
            submissions.finish(attempt: attempt, outcome: .accepted)
            message = accepted
        } catch {
            submissions.finish(attempt: attempt, outcome: Task.isCancelled ? .interrupted : .failed)
            message = Task.isCancelled
                ? "Stopped waiting for laptop acceptance. Your list is saved; check the workflow for receipt."
                : "Your list is saved. Laptop acceptance is unconfirmed. Check the connection and workflow before retrying."
        }
    }
    var body: some View {
        Form {
            Section("Step 1 · Add a video") {
                TextField("Character names (optional)", text: $name).accessibilityLabel("Character names")
                TextField("Paste YouTube link", text: $link).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                Button("Add Video", action: add).disabled(link.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            Section("Your list · \(videos.count) videos") {
                if videos.isEmpty { Text("Add a video above to start your list.").foregroundStyle(.secondary) }
                ForEach(videos) { video in
                    VStack(alignment: .leading) {
                        Text(video.name.isEmpty ? "Video " + video.id : video.name).font(.headline)
                        Text(video.url).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        NavigationLink("View laptop workflow") { VideoWorkflowView(videoID: video.id) }
                            .font(.caption)
                    }
                }.onDelete { offsets in videos.remove(atOffsets: offsets); persist() }
            }
            Section("Step 2 · Export your list") {
                Button("Prepare Updated List", action: exportList).disabled(videos.isEmpty)
                if let exported { ShareLink(item: exported) { Label("Share List", systemImage: "square.and.arrow.up") } }
                Button(sending ? "Sending…" : "Send List to Laptop") {
                    manualSend = Task { @MainActor in await sendList(videos) }
                }.disabled(sending || videos.isEmpty)
                Text("Your laptop address is included. Connect Tailscale on both devices using the same account, then tap Send List to Laptop. No JSON selection is needed. Voice creation and review are separate steps. Offline speech does not need this connection.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Laptop workflow") {
                NavigationLink { VideoWorkflowView() } label: {
                    Label("Live video workflow", systemImage: "list.bullet.rectangle")
                }.accessibilityIdentifier("live-video-workflow")
                Text("See laptop receipt, review pauses, preparation, voice processing and checks. Voice transfer and saving are recorded separately in Voices → Live sync log.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if !submissions.events.isEmpty {
                Section("Phone sending log · latest first") {
                    ForEach(submissions.events.reversed()) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(event.message)
                            Text("\(event.date.formatted(date: .abbreviated, time: .standard)) · iPhone · Send attempt \(event.attempt)")
                                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        }.accessibilityElement(children: .combine)
                    }
                    Text("Only the latest 80 sending events in this view are retained. No video names, links or transcripts are logged here.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if !message.isEmpty { Text(message).accessibilityAddTraits(.updatesFrequently) }
        }.navigationTitle("Video List")
            .task(id: saved) {
                guard !saved.isEmpty else { return }
                do {
                    let pending = try JSONDecoder().decode([QueuedVideo].self, from: saved)
                    guard !pending.isEmpty else { return }
                    try await Task.sleep(nanoseconds: 700_000_000)
                    // A changed list waits for the prior request rather than overlapping it.
                    while sending {
                        try await Task.sleep(nanoseconds: 100_000_000)
                    }
                    await sendList(pending)
                } catch is CancellationError { }
                catch { message = "Your list is saved. The automatic laptop request could not be prepared." }
            }
            .onDisappear { manualSend?.cancel() }
            .onAppear {
                guard !saved.isEmpty else { return }
                do { videos = try JSONDecoder().decode([QueuedVideo].self, from: saved) }
                catch { message = "Your saved list could not be read. Export or recover your list before making changes." }
            }
    }
}
