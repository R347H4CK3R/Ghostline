# VoiceMatrix offline desktop companion

The source now has an executable desktop command workflow, alongside ongoing character preview generation. It is not native iOS inference or a completed graphical app.

Run from the repository root in the tested F5-TTS 1.1.22 environment:

```
python -m tools.voice_studio create --audio reference.wav --metadata voice.json --output voice.vmpack
python -m tools.voice_studio inspect voice.vmpack
python -m tools.voice_studio speak --pack voice.vmpack --text "Your new words" --output speech.wav --checkpoint /path/model_1250000.safetensors --vocoder-directory /path/vocos --vocab /path/vocab.txt
```

Metadata requires `id`, `name`, `categories`, `source`, `permission`, and `referenceText`. Use authorized recordings. The pack includes the reference needed for future synthesis; temporary video downloads may be deleted separately. Packs are reference conditioning, not RVC models. The existing iPhone voice library and installation feeds are unchanged.

The loader requires explicit local model, vocoder and vocabulary files, checks the measured F5 model checksum, and supplies all paths directly to F5-TTS. It does not perform startup Hub lookups or acquire missing weights. A missing or corrupt asset produces an error before model initialization.

The full-video worker reuses private reference transcripts when their source checksum matches. This avoids retranscribing every remaining candidate after a restart. Its local-only initialization repairs the observed startup 403 from remote cache checks. Generated outputs and completed IDs survive restarts. Reference speech and private transcripts must not be committed publicly.

Nine automated tests cover pack integrity, routing the selected reference and new words to the engine, WAV output, temporary reference cleanup, and refusing missing/corrupt synthesis weights. Routing tests use a test engine; actual full-video synthesis is tracked separately in the batch results. They do not establish character resemblance.

Still pending: native iPhone UI/import integration, speaker separation, real RVC training/index generation and independent conversion checks, training export, cancellation, and device verification. No trained model export is claimed by these companion commands.
