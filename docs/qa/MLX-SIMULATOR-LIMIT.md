# MLX simulator boundary

The pinned MLX0.31.6 [iOS documentation](https://github.com/ml-explore/mlx-swift/blob/0.31.6/Source/MLX/Documentation.docc/Articles/running-on-ios.md) states that the iOS Simulator lacks the modern Metal GPU family needed to evaluate MLX arrays. It recommends a real Apple GPU in a Mac destination and actual-device testing. Upstream issues [mlx-swift269](https://github.com/ml-explore/mlx-swift/issues/269) and [mlx2605](https://github.com/ml-explore/mlx/issues/2605) discuss simulator crashes.

A separate simulator F5 attempt in run42450291633 aborted in libc++ with a null C-string assertion. There is no symbolicated stack establishing the precise call site. This supports the documented simulator boundary and does not establish iPhone success or failure.

F5 diagnostic audio is therefore measured on hosted Mac Metal, with networking blocked, using the production adapter and pinned model assets. Full iPhone ARM64 app compilation and package integrity are separate checks. The iOS-target Metal library is built with the iPhoneOS SDK and copied into the app; publication inspection checks its presence and MTLB header. Physical iPhone speech, resource loading and memory remain unverified.

CoreML conversion has a separate iOS simulator host compiling the unchanged production Catalog, ConversionAudio, OfflineVoiceConverter and CharacterVoiceConversion files. It does not link or pretend to execute MLX. The full app continues to build both shared engines. This avoids spending simulator conversion-test time compiling an unrelated unsupported MLX path, without replacing the conversion model or weakening audio/timing/word checks.
