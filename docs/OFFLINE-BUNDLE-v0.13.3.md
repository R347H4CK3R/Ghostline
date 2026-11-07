# GHOSTLINE v0.13.3 -- offline model bundle, not just a catalog

The experimental iOS IPA embeds the complete ONNX/config/model-card files of five en_US Piper model variants:
- LJ Speech (medium) and LJ Speech (high) -- two quality presets from the same public-domain recording corpus and same speaker identity
- Kristin (medium) -- source-documented public-domain source
- Norman (medium) -- public-domain LibriVox recordings
- John (medium) -- LibriVox source; published Kristin lineage

These are four distinct modeled speakers, all still **unverified on a physical iPhone**. The high LJ Speech preset's complete bytes/sha256/model-card are pinned at the immutable rhasspy/piper-voices source revision.

No network or separate per-voice download is required to find the bundled Piper ONNX weights and settings. The runtime still needs an on-device test to prove conversion and audible speech.

The 589 external discovery entries are NOT 589 packaged model files. Many links point to community voice directories or licensed/identity-unverified replicas of performers or protected fictional characters. Some are not downloadable or are not compatible with the local inference engine. They are deliberately not bundled or labeled usable. Do not automatically fetch every listing or redistribute fan character voices without rights.

Further expansion can add fully downloadable, licensed and compatible US-English checkpoints with per-asset SHA-256, source notices and physical device evidence. Offline RVC voice changing remains experimental and private imported RVC files are not included by default.

Audio and usage rights for recognizable actor, singer or character identities must be independently established even if the underlying model uses an open-source architecture.
