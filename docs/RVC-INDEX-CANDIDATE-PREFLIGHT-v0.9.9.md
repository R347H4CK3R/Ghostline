# Experimental private RVC .index candidate preflight — v0.9.9

An imported `.index` is an **unverified local candidate**, not an audio engine or a verified voice. This release adds a bounded FAISS **header-only** probe for common float-index families (including `IwFl` / IVF Flat and `IxF2` / FlatL2). It records the four-character FAISS family, declared vector dimension, and number of vectors, along with an independent SHA-256 of the full file.

**What it does:** rejects obvious non-FAISS files, shortened or implausible headers and empty indexes before replacing any previously attached index. The old file and catalog entry remain intact after an unsuccessful import. Audits recompute the hashes, re-probe the header, and compare saved metadata. Older private JSON catalog records continue to decode with absent optional header fields. Private packs can be searched and filtered by category with no catalog or result-count cap. The ephemeral private-weight route is revoked when the converter closes.

**What it does not do:** deserialize the entire FAISS index, validate the entire inverted-list storage, confirm that the index feature dimension matches a specific `.pth`, perform nearest-neighbor feature retrieval, accelerate inference, verify an actor/character identity, or assert that any voice is licensed or usable on iPhone/Strata. No `.index` bytes are served to the WebAssembly converter. A plausible header can exist in a damaged or malicious file. Not all index families are recognized; unsupported files must be validated separately before a future decoder is added.

### Private physical-device test protocol

1. In the GHOSTLINE RVC Packs tab, import an **authorized** `.pth` file and document its source and voice-use permission. Try a real FAISS IVF Flat `.index`, observe the candidate header metadata, and export the local audit JSON.
2. Try a wrongly renamed WAV/PKL, an empty/truncated index, and a real but unsupported FAISS family. Verify rejection, preservation of the prior index, and no increase in verified voice count.
3. Search and filter a large locally imported catalog by category; confirm that imports outside the visible filter are preserved. Close and reopen the app to verify catalog migration and metadata persistence.
4. Separately verify local ContentVec/RMVPE/RVC conversion with source audio on the target iPhone in airplane mode, listen to the complete WAV, and record model/audio hashes and a reviewer identity assessment. **The FAISS `.index` is not used in that conversion**. Until retrieval is integrated and tested, report index retrieval as unsupported.

CI's deterministic Swift fixtures test bounded header parsing only. Neither CI nor an IPA ZIP check proves physical-device inference, privacy isolation, audible listening, rights approval, or authentic identity. Keep this branch draft and the IPA private.

Reference format: upstream FAISS `faiss/impl/index_write.cpp` and `faiss/impl/index_read.cpp`; FAISS binary index headers begin with a fourcc tag and common dimension/count/metric fields. The header probe intentionally does not link or bundle FAISS.
