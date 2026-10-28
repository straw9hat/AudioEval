# Cost and Latency Analysis

## Measured latency

Hardware: AMD Ryzen 7 5800XT (8 cores), Windows, Python 3.14.2, PyTorch 2.11.0+cpu,
Transformers 5.21.0, faster-whisper 1.2.1. Experiments ran sequentially at one worker.
Per-clip processing time includes decoding, acoustic features, and configured inference;
model download and one-time model loading/startup are excluded. The candidate runs used
the pinned revisions in [MODEL_SETUP.md](../docs/MODEL_SETUP.md).

| File | Audio (s) | Decode (s) | Features (s) | Total (s) | Real-time factor |
| --- | --- | --- | --- | --- | --- |
| call_001.ogg | 30.94 | 0.117 | 0.105 | 0.224 | 0.0072 |
| call_002.ogg | 34.96 | 0.129 | 0.120 | 0.250 | 0.0072 |
| call_003.ogg | 171.92 | 0.598 | 0.602 | 1.207 | 0.0070 |
| **E0 all** | **237.82 (3.96 min)** | | | **1.681** | **0.0071** |

Real-time factor (RTF) = processing seconds / audio seconds. These are warm local
measurements, not hosted latency or a production SLA.
The separate comparative E0 run measured RTF 0.0070; the small difference from this
per-file run (0.0071) is ordinary run-to-run timing variation.

| Experiment | Configuration | RTF | Cost/audio-min at 10% utilization* |
| --- | --- | ---: | ---: |
| E0 | Acoustic baseline | 0.0070 | $0.0000583 |
| E1 | E0 + AudioSet events | 0.0763 | $0.0006358 |
| E2 | E0 + speech emotion | 0.0669 | $0.0005575 |
| E3 | E0 + Whisper-small + GoEmotions | 0.1592 | $0.0013267 |
| E4 | Events + SER + Whisper-small + GoEmotions | 0.3595 | $0.0029958 |
| E6 | E4 with Whisper-base | 0.2527 | $0.0021058 |

E5 (gated overlap model) was not run. The three-call runs are a tiny workload; these RTFs
are per-clip processing measurements, not cold-start, queue, or large-batch benchmarks.

## Cost model

Self-hosted, no paid API:

$$\text{cost per audio minute} = \frac{\text{instance price per hour}}{(60 / \text{RTF}) \times \text{concurrency} \times \text{utilization}}$$

Ceiling: $0.003 per audio minute. These estimates assume one stream, a $0.05/instance-hour
price (not a quote), and the listed sustained utilization:

| Experiment | Cost/audio-min at 100% | At 10% | At 2% | Minimum utilization to meet ceiling |
| --- | ---: | ---: | ---: | ---: |
| E0 | $0.0000058 | $0.0000583 | $0.0002917 | 0.20% |
| E1 | $0.0000636 | $0.0006358 | $0.0031792 (over) | 2.12% |
| E2 | $0.0000558 | $0.0005575 | $0.0027875 | 1.86% |
| E3 | $0.0001327 | $0.0013267 | $0.0066333 (over) | 4.42% |
| E4 | $0.0002996 | $0.0029958 | $0.0149792 (over) | 9.99% |
| E6 | $0.0002106 | $0.0021058 | $0.0105292 (over) | 7.02% |

At this assumed rate, E4 has effectively no margin at 10% utilization; E6 has more
headroom but exceeds the ceiling at 2%. These are not claims about an unselected host.
Replace the assumed hourly price and measured RTF with the actual deployment values.
Reproduce a cost row with `python -m audioeval cost --rtf <rtf> --hourly-price <price>`.

## Assumptions and what is included

- Included: compute time for decoding, features, and any enabled local models.
- Not included: idle hosting, storage, egress, monitoring, model download, and the
  evaluation-period always-on instance. Confirm whether the cost ceiling includes them.
- Low utilization raises cost per audio minute proportionally (the 10% column). For low
  volume, use scale-to-zero hosting outside the evaluation period, or batch work.
- No external paid API is used. If one is added, disclose model, price, retention policy,
  and whether audio leaves AutoAce-controlled infrastructure (brief section 11).

## Conclusion

E0 meets the ceiling with substantial margin under these assumptions. E1/E2/E3 also meet
it at 10% utilization; E4 is borderline and E6 is below the ceiling only above about 7%
utilization at the assumed price. Because no production host price or workload utilization
has been provided, cost compliance on deployment is still unverified. Keep E0 as the
default until a production price/utilization budget and independent accuracy evidence
justify enabling a model configuration.
