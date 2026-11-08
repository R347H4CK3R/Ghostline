import Foundation

// One lease across recording, synthesis and conversion, shared by both studios.
struct StudioActivity {
    enum Kind { case microphone, processing }
    private var owner: (UUID, Kind)?
    var microphoneInUse: Bool { owner?.1 == .microphone }
    var processingInUse: Bool { owner?.1 == .processing }
    mutating func claim(_ kind: Kind) -> UUID? {
        guard owner == nil else { return nil }
        let token = UUID(); owner = (token, kind); return token
    }
    mutating func release(_ token: UUID) {
        guard owner?.0 == token else { return }
        owner = nil
    }
}
