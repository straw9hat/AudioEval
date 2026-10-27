# Local model weights (not committed)

Place downloaded model directories here, for example:

```
models/
  ser/       speech emotion recognition (Hugging Face audio-classification)
  ast/       AudioSet event tagger (Hugging Face audio-classification)
  whisper/   faster-whisper (CTranslate2) model
  text/      text emotion classifier (Hugging Face text-classification)
  overlap/   pyannote overlapped-speech pipeline (config.yaml + weights)
```

Then point `AUDIOEVAL_*_MODEL` at these directories. Full steps: [docs/MODEL_SETUP.md](../docs/MODEL_SETUP.md).
