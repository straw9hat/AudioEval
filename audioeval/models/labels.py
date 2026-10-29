"""Label mappings from common pretrained model vocabularies to the required schema."""

from __future__ import annotations

TONES = ("neutral", "satisfied", "frustrated", "upset", "distressed")

# Speech-emotion-recognition labels (IEMOCAP/RAVDESS/CREMA-D/MSP style) -> tone weights.
# Sad maps partly to frustrated and partly to distressed; there is no exact equivalent.
SER_LABELS: dict[str, dict[str, float]] = {
    "neu": {"neutral": 1.0},
    "neutral": {"neutral": 1.0},
    "calm": {"neutral": 1.0},
    "hap": {"satisfied": 1.0},
    "happy": {"satisfied": 1.0},
    "happiness": {"satisfied": 1.0},
    "joy": {"satisfied": 1.0},
    "pleasant_surprise": {"satisfied": 1.0},
    "ps": {"satisfied": 1.0},
    "ang": {"upset": 1.0},
    "angry": {"upset": 1.0},
    "anger": {"upset": 1.0},
    "dis": {"frustrated": 1.0},
    "disgust": {"frustrated": 1.0},
    "contempt": {"frustrated": 1.0},
    "sad": {"frustrated": 0.5, "distressed": 0.5},
    "sadness": {"frustrated": 0.5, "distressed": 0.5},
    "fea": {"distressed": 1.0},
    "fear": {"distressed": 1.0},
    "fearful": {"distressed": 1.0},
    "sur": {"neutral": 1.0},
    "surprise": {"neutral": 1.0},
    "surprised": {"neutral": 1.0},
    "other": {"neutral": 1.0},
    "unknown": {"neutral": 1.0},
    "<unk>": {"neutral": 1.0},
}

# Text emotion labels (GoEmotions, sentiment models) -> tone weights.
TEXT_LABELS: dict[str, dict[str, float]] = {
    "neutral": {"neutral": 1.0},
    "label_1": {"neutral": 1.0},
    "positive": {"satisfied": 1.0},
    "label_2": {"satisfied": 1.0},
    "negative": {"frustrated": 0.6, "upset": 0.4},
    "label_0": {"frustrated": 0.6, "upset": 0.4},
    "admiration": {"satisfied": 1.0},
    "amusement": {"satisfied": 1.0},
    "approval": {"satisfied": 1.0},
    "caring": {"satisfied": 0.5, "neutral": 0.5},
    "excitement": {"satisfied": 1.0},
    "gratitude": {"satisfied": 1.0},
    "joy": {"satisfied": 1.0},
    "love": {"satisfied": 1.0},
    "optimism": {"satisfied": 1.0},
    "pride": {"satisfied": 1.0},
    "relief": {"satisfied": 1.0},
    "annoyance": {"frustrated": 1.0},
    "disappointment": {"frustrated": 1.0},
    "disapproval": {"frustrated": 1.0},
    "disgust": {"frustrated": 0.5, "upset": 0.5},
    "anger": {"upset": 1.0},
    "fear": {"distressed": 1.0},
    "grief": {"distressed": 1.0},
    "nervousness": {"distressed": 0.7, "frustrated": 0.3},
    "remorse": {"neutral": 1.0},
    "sadness": {"distressed": 0.5, "frustrated": 0.5},
    "embarrassment": {"neutral": 1.0},
    "confusion": {"frustrated": 0.4, "neutral": 0.6},
    "curiosity": {"neutral": 1.0},
    "desire": {"neutral": 1.0},
    "realization": {"neutral": 1.0},
    "surprise": {"neutral": 1.0},
}

# AudioSet labels -> concise noise descriptions. Speech-like customer sounds are excluded.
NOISE_LABELS: dict[str, str] = {
    "Television": "television",
    "Radio": "radio",
    "Music": "music",
    "Musical instrument": "music",
    "Singing": "music",
    "Song": "music",
    "Pop music": "music",
    "Background music": "music",
    "Theme music": "music",
    "Chatter": "background chatter",
    "Babble": "background chatter",
    "Crowd": "background chatter",
    "Hubbub, speech noise, speech babble": "background chatter",
    "Conversation": "background chatter",
    "Child speech, kid speaking": "children",
    "Children playing": "children",
    "Baby cry, infant cry": "baby crying",
    "Static": "static",
    "White noise": "hiss",
    "Pink noise": "hiss",
    "Noise": "hiss",
    "Hum": "electrical hum",
    "Mains hum": "electrical hum",
    "Buzz": "electrical hum",
    "Typing": "keyboard typing",
    "Computer keyboard": "keyboard typing",
    "Typewriter": "keyboard typing",
    "Vehicle": "road noise",
    "Car": "road noise",
    "Traffic noise, roadway noise": "road noise",
    "Motor vehicle (road)": "road noise",
    "Car passing by": "road noise",
    "Engine": "engine noise",
    "Wind": "wind",
    "Wind noise (microphone)": "wind",
    "Rustling leaves": "wind",
    "Dog": "dog barking",
    "Bark": "dog barking",
    "Bow-wow": "dog barking",
    "Mechanical fan": "mechanical noise",
    "Air conditioning": "mechanical noise",
    "Vacuum cleaner": "mechanical noise",
    "Machine": "mechanical noise",
    "Printer": "mechanical noise",
    "Siren": "siren",
    "Emergency vehicle": "siren",
    "Telephone bell ringing": "phone ringing",
    "Ringtone": "phone ringing",
    "Telephone": "phone ringing",
    "Dishes, pots, and pans": "kitchen noise",
    "Cutlery, silverware": "kitchen noise",
    "Water tap, faucet": "running water",
    "Rain": "rain",
    "Crackle": "static",
}

# Free-text noise synonyms used when scoring background_noise_type.
NOISE_SYNONYMS: dict[str, str] = {
    "tv": "television",
    "television": "television",
    "tv audio": "television",
    "music": "music",
    "background music": "music",
    "radio": "radio",
    "office chatter": "background chatter",
    "chatter": "background chatter",
    "background voices": "background chatter",
    "people talking": "background chatter",
    "crowd": "background chatter",
    "babble": "background chatter",
    "static": "static",
    "sharp static": "static",
    "crackling": "static",
    "crackle": "static",
    "line static": "static",
    "hiss": "hiss",
    "white noise": "hiss",
    "hum": "electrical hum",
    "electrical hum": "electrical hum",
    "buzz": "electrical hum",
    "keyboard typing": "keyboard typing",
    "typing": "keyboard typing",
    "road noise": "road noise",
    "traffic": "road noise",
    "car": "road noise",
    "wind": "wind",
    "mechanical noise": "mechanical noise",
    "fan": "mechanical noise",
    "dog barking": "dog barking",
    "dog": "dog barking",
    "children": "children",
    "kids": "children",
}


def map_distribution(scores: dict[str, float], table: dict[str, dict[str, float]]) -> dict[str, float] | None:
    out = dict.fromkeys(TONES, 0.0)
    matched = 0.0
    for label, score in scores.items():
        weights = table.get(label.strip().lower())
        if weights is None:
            continue
        matched += score
        for tone, w in weights.items():
            out[tone] += score * w
    if matched <= 0:
        return None
    return {k: v / matched for k, v in out.items()}


def normalize_noise_type(text: str) -> str:
    key = " ".join(text.strip().lower().split())
    return NOISE_SYNONYMS.get(key, key)
