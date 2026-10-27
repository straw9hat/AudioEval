# Cost and Latency Analysis

## Measured latency (E0, acoustic baseline)

Hardware: Intel Core i7-14700K desktop (20 cores), Windows, Python 3.13, NumPy/SciPy with OpenBLAS.
Command: `python -m audioeval benchmark "<supplied zip>" --out <dir> --hourly-price 0.05`.

| File | Audio (s) | Decode (s) | Features (s) | Total (s) | Real-time factor |
| --- | --- | --- | --- | --- | --- |
| call_001.ogg | 30.9 | 0.075 | 0.069 | 0.145 | 0.0047 |
| call_002.ogg | 35.0 | 0.080 | 0.076 | 0.157 | 0.0045 |
| call_003.ogg | 171.9 | 0.392 | 0.380 | 0.777 | 0.0045 |
| **All** | **237.8 (3.96 min)** | | | **1.08** | **0.0046** |

Real-time factor = processing seconds / audio seconds (one worker, warm process). About
0.27 s of processing per audio minute. A cloud vCPU is typically slower than this desktop
CPU; budget for 2-4x (RTF about 0.01-0.02) until measured on the target host.

Model configurations (E1-E6) are not measured yet. Rough expectations to verify: an AST
event tagger and wav2vec2-base SER each add a few hundredths of RTF on CPU; faster-whisper
small (int8) is likely the largest cost. Record measured values here.

## Cost model

Self-hosted, no paid API:

$$\text{cost per audio minute} = \frac{\text{instance price per hour}}{(60 / \text{RTF}) \times \text{concurrency} \times \text{utilization}}$$

Ceiling: $0.003 per audio minute. The break-even instance price at full utilization is
$0.003 \times 60 / \text{RTF}$.

| Configuration | RTF | Break-even $/hour (100% util.) | Cost at $0.10/h, 100% util. | Cost at $0.10/h, 10% util. |
| --- | --- | --- | --- | --- |
| E0 measured (desktop) | 0.0046 | $39.13 | $0.0000077 | $0.000077 |
| E0 cloud estimate (4x slower) | 0.018 | $10.00 | $0.000030 | $0.00030 |
| Illustrative model stack | 0.10 | $1.80 | $0.00017 | $0.0017 |
| Illustrative model stack | 0.30 | $0.60 | $0.00050 | $0.0050 (over) |

$0.10 per instance-hour is an **assumption** for a small CPU instance, not a quoted price.
Replace it with the actual price of the chosen host and region. Reproduce any row with
`python -m audioeval cost --rtf <rtf> --hourly-price <price>`.

## Assumptions and what is included

- Included: compute time for decoding, features, and any enabled local models.
- Not included in the per-minute figure: idle hosting, storage, egress, monitoring, and
  the evaluation-period always-on instance. These are reported separately because the
  brief's ceiling is stated as inference cost. Confirm with AutoAce whether idle time counts.
- Low utilization raises cost per audio minute proportionally (the 10% column). For low
  volume, use scale-to-zero hosting outside the evaluation period, or batch work.
- No external paid API is used. If one is added, disclose model, price, retention policy,
  and whether audio leaves AutoAce-controlled infrastructure (brief section 11).

## Conclusion

The baseline is far below the ceiling on any reasonable instance. The model stack's
compliance depends on measured RTF and utilization: at RTF 0.3 it stays under the ceiling
only above about 17% utilization on a $0.10/h instance. Measure E1-E6 before choosing.
