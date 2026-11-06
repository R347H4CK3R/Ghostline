import Foundation
import Network
import SwiftUI
import WebKit

/// A loopback-only HTTP server so WebAssembly, module workers and model uploads
/// share a normal same-origin context. No remote voice-processing service is used.
final class GhostlineLocalWebServer {
    private let queue = DispatchQueue(label: "com.ghostline.rvc.http")
    private var listener: NWListener?
    private let root = Bundle.main.bundleURL.appendingPathComponent("RVCWeb", isDirectory: true)
    private(set) var url: URL?

    func start(ready: @escaping (Result<URL, Error>) -> Void) {
        guard FileManager.default.fileExists(atPath: root.appendingPathComponent("index.html").path) else {
            ready(.failure(NSError(domain: "GHOSTLINE", code: 200, userInfo: [
                NSLocalizedDescriptionKey: "Bundled offline RVC web engine not found"
            ])))
            return
        }
        do {
            let parameters = NWParameters.tcp
            parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
            let listener = try NWListener(using: parameters)
            self.listener = listener
            var didComplete = false
            listener.stateUpdateHandler = { [weak self] state in
                guard let self else { return }
                switch state {
                case .ready:
                    guard !didComplete, let port = listener.port,
                          let url = URL(string: "http://127.0.0.1:\(port.rawValue)/") else { return }
                    didComplete = true
                    self.url = url
                    DispatchQueue.main.async { ready(.success(url)) }
                case .failed(let error):
                    guard !didComplete else { return }
                    didComplete = true
                    DispatchQueue.main.async { ready(.failure(error)) }
                default: break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in self?.handle(connection) }
            listener.start(queue: queue)
        } catch {
            DispatchQueue.main.async { ready(.failure(error)) }
        }
    }

    func stop() {
        listener?.cancel()
        listener = nil
        url = nil
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
    @Published var status = "Starting private offline RVC engine..."
    private let server = GhostlineLocalWebServer()
    func begin() {
        guard address == nil else { return }
        server.start { [weak self] result in
            switch result {
            case .success(let url):
                self?.address = url
                self?.status = "Local inference server ready. No internet connection required."
            case .failure(let error):
                self?.status = "Offline RVC engine could not start: \(error.localizedDescription)"
            }
        }
    }
    func end() {
        address = nil
        server.stop()
    }
}

struct GhostlineRVCWebScreen: View {
    @StateObject private var controller = GhostlineOfflineRVCController()
    var body: some View {
        VStack(spacing: 0) {
            if let url = controller.address {
                GhostlineRVCWebView(url: url)
            } else {
                ProgressView()
                    .padding()
                Text(controller.status).font(.footnote).foregroundStyle(.secondary).padding()
            }
        }
        .navigationTitle("Offline RVC Converter")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { controller.begin() }
        .onDisappear { controller.end() }
    }
}

private struct GhostlineRVCWebView: UIViewRepresentable {
    let url: URL
    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.07, green: 0.05, blue: 0.12, alpha: 1)
        view.navigationDelegate = context.coordinator
        view.load(URLRequest(url: url))
        return view
    }
    func updateUIView(_ webView: WKWebView, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(url: url) }
    final class Coordinator: NSObject, WKNavigationDelegate {
        let base: URL
        init(url: URL) { self.base = url }
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
