import Foundation

/// Local connection freshness is independent of the laptop's last job activity.
/// A waiting job can have an old updatedAt while every connection check succeeds.
struct RVCOnlineRefreshSchedule: Sendable {
    enum Freshness: Sendable, Equatable { case neverChecked, recent, stale, disconnected }
    static let interval: TimeInterval = 30
    static let staleAfter: TimeInterval = 60
    private(set) var nextAttempt: Date?
    mutating func didAttempt(at now: Date) { nextAttempt = now.addingTimeInterval(Self.interval) }
    func isDue(at now: Date, visible: Bool, active: Bool, pending: Bool, busy: Bool) -> Bool {
        visible && active && pending && !busy && (nextAttempt == nil || now >= nextAttempt!)
    }
    static func freshness(checkedAt: Date?, now: Date, reachable: Bool) -> Freshness {
        guard let checkedAt else { return .neverChecked }
        guard reachable else { return .disconnected }
        return now.timeIntervalSince(checkedAt) >= staleAfter ? .stale : .recent
    }
}

/// A stale navigation task must not suspend the screen that replaced it.
struct RVCOnlineObservationLease: Sendable {
    private var current: UUID?
    mutating func begin() -> UUID {
        let token = UUID(); current = token; return token
    }
    func owns(_ token: UUID) -> Bool { current == token }
    mutating func end(_ token: UUID) -> Bool {
        guard owns(token) else { return false }
        current = nil; return true
    }
}
