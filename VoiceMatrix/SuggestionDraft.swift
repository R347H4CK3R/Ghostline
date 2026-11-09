import Foundation

enum SuggestionDraft {
    static let prefix = "[VoiceMatrix suggestion] "
    static let listURL = URL(string: "https://github.com/R347H4CK3R/Ghostline/issues?q=is%3Aissue%20%22%5BVoiceMatrix%20suggestion%5D%22%20in%3Atitle")!
    static func url(title: String, details: String) -> URL? {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let details = details.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, !details.isEmpty, title.count <= 100,
              title.utf8.count + details.utf8.count <= 2500 else { return nil }
        var components = URLComponents(string: "https://github.com/R347H4CK3R/Ghostline/issues/new")!
        components.queryItems = [
            URLQueryItem(name: "title", value: prefix + title),
            URLQueryItem(name: "body", value: details)
        ]
        return components.url
    }
}
