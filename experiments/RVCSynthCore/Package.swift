// swift-tools-version: 5.9
import PackageDescription

// Isolated native inference boundary. Not linked into VoiceMatrix until the
// complete frontend and trained-graph parity have passed separately.
let package = Package(
    name: "RVCSynthCore",
    platforms: [.iOS(.v15), .macOS(.v14)],
    products: [.library(name: "RVCSynthCore", targets: ["RVCSynthCore"]),
               .executable(name: "RVCContractDiagnostic", targets: ["RVCContractDiagnostic"])],
    targets: [
        .binaryTarget(name: "onnxruntime",
            url: "https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.24.2.zip",
            checksum: "f7100a992d2a8135168c8afd831e6a58b465349101982aa58b3e11d36e600b54"),
        .target(name: "RVCSynthCore", dependencies: ["onnxruntime"],
            path: "Sources/RVCSynthCore", publicHeadersPath: "include"),
        .executableTarget(name: "RVCContractDiagnostic", dependencies: ["RVCSynthCore"],
            path: "Tests")
    ],
    cxxLanguageStandard: .cxx17
)
