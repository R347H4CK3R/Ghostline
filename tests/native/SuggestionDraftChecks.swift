import Foundation
@main struct SuggestionDraftChecks {
    static func main() {
        precondition(SuggestionDraft.url(title: "", details: "Request") == nil)
        precondition(SuggestionDraft.url(title: "Request", details: " ") == nil)
        precondition(SuggestionDraft.url(title: "Request", details: String(repeating: "x", count: 2501)) == nil)
        let title = "Speed & pitch? #1 🎵"
        let body = "Please add controls.\nUse a=b & c? # no automatic attachments."
        let url = SuggestionDraft.url(title: title, details: body)!
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        precondition(components.scheme == "https" && components.host == "github.com")
        precondition(components.path == "/R347H4CK3R/Ghostline/issues/new")
        precondition(components.queryItems?.count == 2)
        precondition(components.queryItems?.first(where: { $0.name == "title" })?.value == SuggestionDraft.prefix + title)
        precondition(components.queryItems?.first(where: { $0.name == "body" })?.value == body)
        precondition(components.user == nil && components.password == nil)
        print("Suggestion draft validates limits and exactly preserves user-authored fields without metadata")
    }
}
