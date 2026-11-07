import Darwin
import Foundation
import XCTest

enum ProcessMemoryProbe {
    static func physicalFootprint() -> UInt64 {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
        let result = withUnsafeMutablePointer(to: &info) { value in
            value.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        return result == KERN_SUCCESS ? info.phys_footprint : 0
    }
}
actor SampledMemoryPeak {
    private var peak: UInt64 = 0
    func sample() { peak = max(peak, ProcessMemoryProbe.physicalFootprint()) }
    func bytes() -> UInt64 { peak }
}
final class MemoryProbeTests: XCTestCase {
    func testOwnProcessFootprintIsAvailable() { XCTAssertGreaterThan(ProcessMemoryProbe.physicalFootprint(), 0) }
}
