"""Optional pretrained model adapters.

Weights are NOT bundled or downloaded at runtime. Each adapter loads from a local
directory configured via AUDIOEVAL_*_MODEL. Missing directories or packages leave
the adapter disabled and the deterministic acoustic baseline is used instead.
See docs/MODEL_SETUP.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings

# Never reach out to the Hugging Face Hub from the service; audio stays local and
# model loading must not depend on network access.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


@dataclass
class ModelBundle:
    emotion: Any = None
    events: Any = None
    asr: Any = None
    text: Any = None
    overlap: Any = None
    status: dict = field(default_factory=dict)

    @property
    def names(self) -> dict:
        return {k: getattr(getattr(self, k), "name", None) for k in ("emotion", "events", "asr", "text", "overlap")}


def _try(bundle: ModelBundle, key: str, path: str, factory) -> None:
    if not path:
        bundle.status[key] = "not configured"
        return
    if not os.path.isdir(path):
        bundle.status[key] = f"directory not found: {path}"
        return
    try:
        setattr(bundle, key, factory(path))
        bundle.status[key] = "loaded"
    except ImportError as exc:
        bundle.status[key] = f"missing package: {exc.name or exc}"
    except Exception as exc:  # report instead of crashing the service
        bundle.status[key] = f"failed to load: {type(exc).__name__}: {exc}"


def load_models(settings: Settings) -> ModelBundle:
    bundle = ModelBundle()

    def emotion(path):
        from .emotion_audio import AudioEmotionModel
        return AudioEmotionModel(path, settings.device)

    def events(path):
        from .audio_events import AudioEventModel
        return AudioEventModel(path, settings.device)

    def asr(path):
        from .asr_text import WhisperASR
        return WhisperASR(path, settings.device)

    def text(path):
        from .asr_text import TextEmotionModel
        return TextEmotionModel(path, settings.device)

    def overlap(path):
        from .overlap import OverlapModel
        return OverlapModel(path, settings.device)

    _try(bundle, "emotion", settings.emotion_model, emotion)
    _try(bundle, "events", settings.event_model, events)
    _try(bundle, "asr", settings.asr_model, asr)
    _try(bundle, "text", settings.text_model, text)
    _try(bundle, "overlap", settings.overlap_model, overlap)
    if bundle.text is not None and bundle.asr is None:
        bundle.status["text"] = "loaded but unused: requires asr model"
    return bundle
