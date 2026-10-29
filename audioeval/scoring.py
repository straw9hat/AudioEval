"""Scoring predictions against labels: accuracy, macro F1, per-class metrics, confusion matrices."""

from __future__ import annotations

from .models.labels import normalize_noise_type
from .schema import AUDIO_QUALITIES, EMOTIONAL_TONES, INTENSITIES, NOISE_SEVERITIES

CATEGORICAL = {
    "emotional_tone": EMOTIONAL_TONES,
    "emotional_intensity": INTENSITIES,
    "background_noise_severity": NOISE_SEVERITIES,
    "audio_quality": AUDIO_QUALITIES,
    "background_noise_present": (True, False),
    "speaker_overlap_present": (True, False),
    "long_silence_present": (True, False),
}


def field_metrics(y_true: list, y_pred: list, classes) -> dict:
    classes = list(classes)
    matrix = {str(t): {str(p): 0 for p in classes} for t in classes}
    for t, p in zip(y_true, y_pred):
        if t in classes and p in classes:
            matrix[str(t)][str(p)] += 1
    per_class = {}
    f1s = []
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        support = tp + fn
        predicted = tp + fp
        prec = tp / predicted if predicted else None
        rec = tp / support if support else None
        f1 = (2 * prec * rec / (prec + rec) if prec and rec else 0.0) if prec is not None and rec is not None else None
        per_class[str(c)] = {"precision": prec, "recall": rec, "f1": f1, "support": support}
        if support or predicted:  # union of true and predicted classes, as in scikit-learn
            f1s.append(f1 or 0.0)
    n = len(y_true)
    return {
        "n": n,
        "accuracy": sum(t == p for t, p in zip(y_true, y_pred)) / n if n else None,
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "macro_f1_classes": [str(c) for c in classes if per_class[str(c)]["support"] or str(c) in {str(p) for p in y_pred}],
        "unsupported_classes": [str(c) for c in classes if not per_class[str(c)]["support"]],
        "per_class": per_class,
        "confusion_matrix": matrix,  # rows = true, columns = predicted
    }


def score(pairs: list[tuple[str, dict, dict]]) -> dict:
    """pairs: (name, prediction, label). Only fields present in a label are scored."""
    report: dict = {"n_scored": len(pairs), "fields": {}}
    for field, classes in CATEGORICAL.items():
        rows = [(pred[field], label[field]) for _, pred, label in pairs if field in label]
        if rows:
            report["fields"][field] = field_metrics([t for _, t in rows], [p for p, _ in rows], classes)
    noise = "background_noise_type"
    rows = [(pred[noise], label[noise]) for _, pred, label in pairs if noise in label]
    if rows:
        exact = sum(p.strip().lower() == t.strip().lower() for p, t in rows)
        norm = sum(normalize_noise_type(p) == normalize_noise_type(t) for p, t in rows)
        report["fields"][noise] = {
            "n": len(rows),
            "exact_match": exact / len(rows),
            "normalized_match": norm / len(rows),
            "note": "normalized_match uses the synonym table in models/labels.py; human review recommended",
        }
    report["per_file"] = [
        {
            "name": name,
            "mismatches": {
                f: {"expected": label[f], "predicted": pred.get(f)}
                for f in label
                if f != "confidence" and pred.get(f) != label[f]
            },
        }
        for name, pred, label in pairs
    ]
    return report
