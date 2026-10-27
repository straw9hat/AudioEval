"""Cost model: inference cost per audio minute for self-hosted compute."""

from __future__ import annotations

CEILING_PER_MIN = 0.003


def cost_per_audio_minute(real_time_factor: float, hourly_price: float, utilization: float = 1.0, concurrency: int = 1) -> float:
    """real_time_factor = processing seconds / audio seconds for one worker.

    One instance processes `concurrency` streams at once; utilization < 1 spreads the
    cost of idle time over the audio actually processed.
    """
    if real_time_factor <= 0 or hourly_price < 0 or not 0 < utilization <= 1 or concurrency < 1:
        raise ValueError("invalid cost inputs")
    audio_minutes_per_hour = 60.0 / real_time_factor * concurrency * utilization
    return hourly_price / audio_minutes_per_hour


def cost_table(real_time_factor: float, hourly_price: float, concurrency: int = 1) -> list[dict]:
    rows = []
    for util in (1.0, 0.5, 0.1, 0.02):
        c = cost_per_audio_minute(real_time_factor, hourly_price, util, concurrency)
        rows.append({"utilization": util, "cost_per_audio_minute": c, "within_ceiling": c <= CEILING_PER_MIN})
    return rows
