# Updating the native Voices folder

The desktop companion can now publish real reference packs into an existing importable collection:

```sh
python -m tools.voice_studio publish-folder --master /path/to/Voices first.vmpack second.vmpack
```

New IDs are added as complete native-format folders. The final `collection.json` update is atomic and occurs after validation and profile installation. Existing voices and categories are preserved. Repeating the same pack is harmless. Duplicate IDs in one batch, repeated exact reference hashes under different names, corrupt packs, unsafe folders and conflicting interrupted publications are rejected. The publisher locks one canonical master path, including relative aliases.

A changed pack for an existing ID is saved separately under sibling `Voices-Candidates/<id>/<revision>/`; it does not replace the active profile or appear in the active collection index. This prevents a retry from silently replacing a previously accepted voice. Candidate promotion and app-to-laptop review feedback remain future integration work; this command does not fabricate listening approval or automatically promote a candidate.

Imported app copies continue working when the external folder disappears. After new additions, refresh/re-import the same Voices folder to copy them into the app. The app's existing foreground refresh can use its saved local folder authorization; this command does not provide network synchronization from the laptop.

The exclusive local-file lock coordinates this publisher's instances. New profile files and the index are flushed before publication; POSIX directory barriers are also used. Directory flushing is unavailable through this Python path on Windows, so sudden power-loss durability is not guaranteed. Process interruption can leave unindexed folders, which are reused only if they exactly match the next publication; conflicting originals are never overwritten. Keep ordinary storage backups.

The command validates reusable F5 reference conditioning and native folder structure, not character identity, engine execution, intelligibility or redistribution permission. Its report explicitly leaves native iOS verification false. Shared runtime/weights and individual listening/device tests are separate. No private references are committed or included in the IPA by this change.

Tests use synthetic audio, real files and the actual command. Hosted checks cover Windows/Linux publication and production Swift folder import on macOS. Automatic video acquisition, speaker/label review, neural generation, validated queue completion/ledger cleanup and private master-folder transport are still unfinished. The published 0.4.0 app and release feeds are unchanged.
