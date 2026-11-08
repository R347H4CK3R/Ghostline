# Separate character folders

The source now has a native folder picker at Home → My Character Folder. It selects the collection folder rather than individual JSON. The Python companion exports it with:

```sh
python -m tools.voice_studio export-folder --output Voices-revision-1 first.vmpack second.vmpack
```

This writes collection.json plus one directory per stable character ID, each containing manifest.json and reference.wav. Existing export destinations are preserved; export a new revision folder. The importer copies validated profiles privately, atomically commits its index, rejects repeated IDs or exact reference audio under another name, and preserves missing previously imported voices. A saved folder bookmark allows refresh on launch/foreground; an unavailable folder never deletes cached profiles. Favorites are not modified.

These are reusable F5 reference-conditioning profiles, not trained RVC weights. The collection does not include the shared F5 engine. Import alone does not establish native synthesis, voice conversion, permissions, or likeness verification. Source/permission strings are records, not proof of authorization. Imported profiles remain separate from bundled Phonon voices and cannot silently fall back to a stock speaker.

Native F5 ARM64 compile probe succeeded in Actions run 42439047361 at f0dc2e845c373a393c2fec8a40c682f8e2881589. Native synthesis, model loading/memory on iPhone, conversion, and real listening review still require verification. The folder import checks use synthetic PCM fixtures; those checks do not generate or verify character speech.
