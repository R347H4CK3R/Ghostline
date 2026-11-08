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
    @State private var pairing = false
    @State private var sending = false

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
                    }
                }.onDelete { offsets in videos.remove(atOffsets: offsets); persist() }
            }
            Section("Step 2 · Export your list") {
                Button("Prepare Updated List", action: exportList).disabled(videos.isEmpty)
                if let exported { ShareLink(item: exported) { Label("Share List", systemImage: "square.and.arrow.up") } }
                Button("Connect Laptop") { pairing = true }
                Button(sending ? "Sending…" : "Send List to Laptop") {
                    sending = true
                    Task { @MainActor in
                        defer { sending = false }
                        do {
                            let data = try JSONEncoder().encode(["videos": videos])
                            message = try await LaptopConnection.send(data)
                        } catch { message = error.localizedDescription }
                    }
                }.disabled(sending || videos.isEmpty)
                Text("Connect using your laptop companion’s HTTPS pairing file. Sending adds requests to its queue; voice creation and review are separate steps. Offline speech does not need this connection.").font(.caption).foregroundStyle(.secondary)
            }
            if !message.isEmpty { Text(message).accessibilityAddTraits(.updatesFrequently) }
        }.navigationTitle("Video List")
            .fileImporter(isPresented: $pairing, allowedContentTypes: [.item]) { result in
                do { try LaptopConnection.pair(from: result.get()); message = "Laptop connection saved. Send your list when ready." }
                catch { message = error.localizedDescription }
            }
            .onAppear {
                guard !saved.isEmpty else { return }
                do { videos = try JSONDecoder().decode([QueuedVideo].self, from: saved) }
                catch { message = "Your saved list could not be read. Export or recover your list before making changes." }
            }
    }
}
