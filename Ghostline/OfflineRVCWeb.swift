import Foundation
import AVFoundation
import CryptoKit
import Network
import SwiftUI
import WebKit

/// A loopback-only HTTP server so WebAssembly, module workers and model uploads
/// share a normal same-origin context. No remote voice-processing service is used.
final class GhostlineLocalWebServer: @unchecked Sendable {
    private let stateLock = NSLock()
    private var startCompleted = false
    private var generation = 0
    private let queue = DispatchQueue(label: "com.ghostline.rvc.http")
    private var listener: NWListener?
    private let root = Bundle.main.bundleURL.appendingPathComponent("RVCWeb", isDirectory: true)
    private(set) var url: URL?

    func start(ready: @escaping @Sendable (Result<URL, Error>) -> Void) {
        guard FileManager.default.fileExists(atPath: root.appendingPathComponent("index.html").path) else {
            ready(.failure(NSError(domain: "GHOSTLINE", code: 200, userInfo: [
                NSLocalizedDescriptionKey: "Bundled offline RVC web engine not found"
            ])))
            return
        }
        stateLock.lock()
        generation += 1
        let session = generation
        startCompleted = false
        stateLock.unlock()
        do {
            let parameters = NWParameters.tcp
            parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
            let listener = try NWListener(using: parameters)
            self.listener = listener
            listener.stateUpdateHandler = { [weak self, weak listener] state in
                guard let self else { return }
                switch state {
                case .ready:
                    guard let port = listener?.port,
                          let url = URL(string: "http://127.0.0.1:\(port.rawValue)/") else { return }
                    self.url = url
                    self.finishStart(.success(url), session: session, ready: ready)
                case .failed(let error):
                    self.finishStart(.failure(error), session: session, ready: ready)
                default: break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in self?.handle(connection) }
            listener.start(queue: queue)
        } catch {
            finishStart(.failure(error), session: session, ready: ready)
        }
    }

    private func finishStart(_ result: Result<URL, Error>,
                             session: Int,
                             ready: @escaping @Sendable (Result<URL, Error>) -> Void) {
        stateLock.lock()
        guard generation == session, !startCompleted else {
            stateLock.unlock()
            return
        }
        startCompleted = true
        if case .failure = result {
            listener?.cancel()
            listener = nil
            url = nil
        }
        stateLock.unlock()
        DispatchQueue.main.async { ready(result) }
    }

    func stop() {
        stateLock.lock()
        generation += 1 // invalidate callbacks from the previous listener
        startCompleted = false
        let previous = listener
        listener = nil
        url = nil
        stateLock.unlock()
        previous?.cancel()
    }

    private func handle(_ connection: NWConnection) {
        connection.start(queue: queue)
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16_384) { [weak self] data, _, _, error in
            guard let self else { connection.cancel(); return }
            guard error == nil, let data, let request = String(data: data, encoding: .utf8),
                  let firstLine = request.components(separatedBy: "\r\n").first else {
                connection.cancel(); return
            }
            let tokens = firstLine.split(separator: " ")
            guard tokens.count >= 2, tokens[0] == "GET" || tokens[0] == "HEAD" else {
                self.sendError(connection, code: 405, message: "Method Not Allowed"); return
            }
            let rawPath = String(tokens[1]).components(separatedBy: "?")[0]
            guard let path = rawPath.removingPercentEncoding, !path.contains("\\"),
                  !path.contains("\0"), !path.split(separator: "/").contains("..") else {
                self.sendError(connection, code: 400, message: "Bad Request"); return
            }
            let fileName = path == "/" ? "index.html" : String(path.drop(while: { $0 == "/" }))
            let target = self.root.appendingPathComponent(fileName).standardizedFileURL
            guard target.path.hasPrefix(self.root.standardizedFileURL.path + "/"),
                  let attrs = try? FileManager.default.attributesOfItem(atPath: target.path),
                  (attrs[.type] as? FileAttributeType) == .typeRegular,
                  let size = (attrs[.size] as? NSNumber)?.uint64Value else {
                self.sendError(connection, code: 404, message: "Not Found"); return
            }
            let ext = target.pathExtension.lowercased()
            let mime: String
            switch ext {
            case "html": mime = "text/html; charset=utf-8"
            case "js", "mjs": mime = "text/javascript; charset=utf-8"
            case "css": mime = "text/css; charset=utf-8"
            case "wasm": mime = "application/wasm"
            case "json": mime = "application/json"
            case "md", "txt": mime = "text/plain; charset=utf-8"
            case "svg": mime = "image/svg+xml"
            case "png": mime = "image/png"
            default: mime = "application/octet-stream"
            }
            let headers = "HTTP/1.1 200 OK\r\nContent-Type: \(mime)\r\nContent-Length: \(size)\r\nConnection: close\r\nCross-Origin-Opener-Policy: same-origin\r\nCross-Origin-Embedder-Policy: require-corp\r\nCross-Origin-Resource-Policy: same-origin\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n"
            connection.send(content: Data(headers.utf8), completion: .contentProcessed { sendError in
                guard sendError == nil else { connection.cancel(); return }
                if tokens[0] == "HEAD" { connection.cancel(); return }
                guard let file = try? FileHandle(forReadingFrom: target) else { connection.cancel(); return }
                self.sendFile(connection, from: file)
            })
        }
    }

    private func sendFile(_ connection: NWConnection, from file: FileHandle) {
        do {
            guard let data = try file.read(upToCount: 64 * 1024), !data.isEmpty else {
                try? file.close()
                connection.cancel()
                return
            }
            connection.send(content: data, completion: .contentProcessed { [weak self] error in
                if error == nil { self?.sendFile(connection, from: file) }
                else { try? file.close(); connection.cancel() }
            })
        } catch {
            try? file.close()
            connection.cancel()
        }
    }

    private func sendError(_ connection: NWConnection, code: Int, message: String) {
        let body = Data(message.utf8)
        let headers = "HTTP/1.1 \(code) \(message)\r\nContent-Type: text/plain\r\nContent-Length: \(body.count)\r\nConnection: close\r\n\r\n"
        connection.send(content: Data(headers.utf8) + body, completion: .contentProcessed { _ in connection.cancel() })
    }
}

/// The web runtime holds an RVC v2 inference pipeline, not merely an ONNX graph probe.
/// The user supplies ContentVec, RMVPE, converted RVC weights, and source audio locally.
@MainActor
final class GhostlineOfflineRVCController: ObservableObject {
    @Published var address: URL?
    @Published var latestWAV: URL?
    @Published var status = "Starting private offline RVC engine..."
    @Published var hasStartError = false
    @Published var isStarting = false
    @Published var diagnosticsURL: URL?
    @Published private(set) var playbackStarted = false
    @Published private(set) var userAttestedListening = false
    @Published var playbackStatus = ""
    private var player: AVAudioPlayer?
    private let server = GhostlineLocalWebServer()
    private var sessionID = UUID()
    private var events: [[String: String]] = []
    private var savedWAV: [String: Any]?

    private func event(_ kind: String, _ detail: String) {
        // Never offer a stale JSON export after new events or a new WAV.
        diagnosticsURL = nil
        if events.count >= 200 { events.removeFirst() }
        events.append([
            "at_utc": ISO8601DateFormatter().string(from: Date()),
            "kind": kind,
            "detail": String(detail.prefix(250))
        ])
    }

    func recordWebStatus(_ message: String) {
        status = String(message.prefix(250))
        event("web_status", status)
    }

    func begin() {
        guard address == nil, !isStarting else { return }
        isStarting = true
        hasStartError = false
        status = "Starting private offline RVC engine..."
        let session = UUID()
        sessionID = session
        event("server_start", "Opening bundled RVC runtime on loopback only")
        server.start { [weak self] result in
            Task { @MainActor [weak self] in
                guard let self, self.sessionID == session else { return }
                self.isStarting = false
                switch result {
                case .success(let url):
                    self.address = url
                    self.status = "Local inference server ready. Audio generation not yet verified."
                    self.event("server_ready", "Loopback RVC resources available")
                case .failure(let error):
                    self.hasStartError = true
                    self.status = "Offline RVC engine could not start: \(error.localizedDescription)"
                    self.event("server_error", error.localizedDescription)
                }
            }
        }
    }

    /// Exportable machine-readable device session events do not certify voice identity.
    func exportDiagnostics() {
        let report: [String: Any] = [
            "schema_version": 2,
            "record_type": "ghostline_private_rvc_web_session_diagnostic",
            "generated_utc": ISO8601DateFormatter().string(from: Date()),
            "bundle_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
            "events": events,
            "saved_wav": savedWAV as Any? ?? NSNull(),
            "device_audio_playback_started": playbackStarted,
            "user_attested_listening": userAttestedListening,
            "airplane_mode_confirmed": false,
            "target_device_audio_listening_confirmed": false,
            "voice_identity_verified": false,
            "voice_rights_independently_verified": false,
            "rvc_index_retrieval_integrated": false
        ]
        do {
            let bytes = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("GHOSTLINE-RVC-private-diagnostic-\(UUID().uuidString).json")
            try bytes.write(to: url, options: .atomic)
            diagnosticsURL = url
            status = "Private diagnostics prepared. This does not establish working or authentic voices."
        } catch {
            status = "Diagnostics export failed: \(error.localizedDescription)"
        }
    }

    func receiveAudio(dataURL: String) {
        guard dataURL.hasPrefix("data:audio/") || dataURL.hasPrefix("data:application/octet-stream;") else {
            status = "Export rejected: unexpected data type."
            event("wav_export_rejected", "Unexpected MIME type")
            return
        }
        guard let comma = dataURL.firstIndex(of: ","),
              let decoded = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])),
              decoded.count > 44, decoded.count < 80_000_000 else {
            status = "Export rejected: missing, oversized or invalid audio."
            event("wav_export_rejected", "Invalid base64 payload or size")
            return
        }
        do {
            let info = try GhostlineWAVInspector.inspect(decoded)
            // A newly generated recording must never inherit listening evidence
            // from the preceding WAV, even within the same converter session.
            player?.stop()
            player = nil
            playbackStarted = false
            userAttestedListening = false
            playbackStatus = "Not played in the native audio player yet."
            let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("GHOSTLINE-Exports", isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let file = dir.appendingPathComponent("RVC-\(UUID().uuidString).wav")
            try decoded.write(to: file, options: .atomic)
            let digest = SHA256.hash(data: decoded).map { String(format: "%02x", $0) }.joined()
            latestWAV = file
            savedWAV = [
                "sha256": digest, "bytes": decoded.count,
                "sample_rate_hz": info.sampleRate, "channels": info.channels,
                "bits_per_sample": info.bitsPerSample, "audio_frames": info.audioFrames,
                "duration_seconds": info.durationSeconds,
                "wav_structure_validated": true,
                "nonzero_pcm_bytes": true,
                "device_audio_playback_started": false,
                "user_attested_listening": false,
                "speaker_identity_verified": false
            ]
            event("wav_export_saved", "WAV validated and saved; SHA-256: " + digest)
            status = "Offline RVC WAV saved (\(String(format: "%.1f", info.durationSeconds))s, \(info.sampleRate) Hz). Listen to verify quality."
        } catch {
            status = "Export rejected: \(error.localizedDescription)"
            event("wav_export_rejected", error.localizedDescription)
        }
    }

    func playSavedWAV() {
        guard let file = latestWAV else { return }
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
            let replay = try AVAudioPlayer(contentsOf: file)
            guard replay.duration > 0.2, replay.prepareToPlay(), replay.play() else {
                throw NSError(domain: "GHOSTLINE.RVC", code: 301,
                              userInfo: [NSLocalizedDescriptionKey: "Native playback did not start"])
            }
            player?.stop()
            player = replay
            playbackStarted = true
            savedWAV?["device_audio_playback_started"] = true
            event("wav_playback_started", "AVAudioPlayer started replay of saved WAV")
            playbackStatus = "Playing saved WAV. Starting playback does not prove anyone listened."
        } catch {
            playbackStatus = "Native WAV playback failed: \(error.localizedDescription)"
            event("wav_playback_failed", error.localizedDescription)
        }
    }

    func attestListening() {
        guard playbackStarted, latestWAV != nil, !userAttestedListening else { return }
        userAttestedListening = true
        savedWAV?["user_attested_listening"] = true
        event("user_attested_listening", "User confirmed hearing the saved WAV on this device")
        playbackStatus = "Listening acknowledged for this WAV. Identity, rights and offline isolation are still unverified."
    }

    func end() {
        player?.stop()
        player = nil
        sessionID = UUID() // ignore callbacks queued before leaving the screen
        address = nil
        isStarting = false
        hasStartError = false
        event("server_stop", "Local loopback server stopped")
        server.stop()
    }
}

struct GhostlineRVCWebScreen: View {
    @StateObject private var controller = GhostlineOfflineRVCController()
    var body: some View {
        VStack(spacing: 0) {
            if let url = controller.address {
                GhostlineRVCWebView(url: url, controller: controller)
            } else {
                if controller.hasStartError {
                    Button("Retry offline RVC engine") { controller.begin() }
                        .buttonStyle(.borderedProminent)
                        .padding()
                } else {
                    ProgressView().padding()
                }
                Text(controller.status).font(.footnote).foregroundStyle(.secondary).padding()
            }
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 6) {
                if let wav = controller.latestWAV {
                    Button("Play saved WAV on iPhone") { controller.playSavedWAV() }
                        .buttonStyle(.borderedProminent)
                    if controller.playbackStarted {
                        Button(controller.userAttestedListening ? "Listening acknowledged" : "I heard this WAV on this device") {
                            controller.attestListening()
                        }
                        .disabled(controller.userAttestedListening)
                        .buttonStyle(.bordered)
                    }
                    if !controller.playbackStatus.isEmpty {
                        Text(controller.playbackStatus).font(.caption).foregroundStyle(.secondary)
                    }
                    ShareLink(item: wav) {
                        Label("Share locally generated WAV", systemImage: "square.and.arrow.up")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                }
                Button("Prepare private diagnostics JSON") { controller.exportDiagnostics() }
                    .buttonStyle(.bordered)
                if let report = controller.diagnosticsURL {
                    ShareLink(item: report) {
                        Label("Export private diagnostics", systemImage: "doc.text")
                    }
                }
            }
            .padding(10)
        }
        .navigationTitle("Offline RVC Converter")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { controller.begin() }
        .onDisappear { controller.end() }
    }
}

private struct GhostlineRVCWebView: UIViewRepresentable {
    let url: URL
    let controller: GhostlineOfflineRVCController
    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        configuration.userContentController.add(context.coordinator, name: "ghostline")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.07, green: 0.05, blue: 0.12, alpha: 1)
        view.navigationDelegate = context.coordinator
        view.load(URLRequest(url: url))
        return view
    }
    func updateUIView(_ webView: WKWebView, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(url: url, controller: controller) }
    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        let base: URL
        weak var controller: GhostlineOfflineRVCController?
        init(url: URL, controller: GhostlineOfflineRVCController) {
            self.base = url
            self.controller = controller
        }
        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard let value = message.body as? [String: Any],
                  let kind = value["kind"] as? String else { return }
            if kind == "status", let status = value["message"] as? String {
                Task { @MainActor [weak self] in self?.controller?.recordWebStatus(status) }
            } else if kind == "wav", let wav = value["dataURL"] as? String {
                Task { @MainActor [weak self] in self?.controller?.receiveAudio(dataURL: wav) }
            }
        }
        func webView(_ webView: WKWebView,
                     decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let destination = action.request.url else { decisionHandler(.cancel); return }
            if destination.scheme == "blob" ||
               (destination.host == "127.0.0.1" && destination.port == base.port) {
                decisionHandler(.allow)
            } else {
                decisionHandler(.cancel)
            }
        }
    }
}
