# Adaptive Capacity (One‑Pager)

This repo implements an adaptive capacity profile across four dimensions using geometric means:

- Form: SPI (Structure Productivity Index) and OV (Option Value)
- Function: IER (Intent Effectiveness Ratio)
- Behavior: RE (Recovery Elasticity) and REL (Resource Elasticity)
- Context: ABS (Adaptive Baseline Stability)

Roll‑up uses geometric mean for per‑dimension and overall headline:

- A_form = gmean([spi, ov])
- A_function = gmean([ier])
- A_behavior = gmean([re, rel])
- A_context = gmean([abs])
- A_headline = gmean([A_form^w_form, A_function^w_func, A_behavior^w_beh, A_context^w_ctx]) with equal weights by default

Current thresholds

- Baseline (samples/thresholds.health.json)
  - spi ≥ 0.10, ier ≥ 0.30, abs ≥ 0.30, re ≥ 0.0005
  - ov ≥ 0.20, rel ≥ 0.20, A_headline ≥ 0.50

- Strict (azure/thresholds.strict.json)
  - spi ≥ 0.50, ier ≥ 0.70, abs ≥ 0.70, re ≥ 0.05
  - ov ≥ 0.50, rel ≥ 0.60, A_headline ≥ 0.80

CLI quickstart

- Azure slice (with config):
  - `npm run health:azure`
  - `npm run health:azure:check` (validates against azure/thresholds.json)
  - `npm run health:azure:strict` (CI gate option)

- Samples:
  - `npm run health:smoke`
  - `npm run health:check`

Compact dashboard JSON

- Add `--compact` to the CLI to emit a concise JSON including window bounds:

  `{ "spi":0.66,"ov":0.50,"ier":0.50,"re":0.30,"rel":0.67,"abs":0.50, "A_form":0.577,"A_function":0.50,"A_behavior":0.448,"A_context":0.50,"A_headline":0.504, "window":{ "start":1736880600000, "end":1736881500000 } }`

Notes

- REL requires either `slo_ok` points after `t0`, or latency values plus a `latencyThreshold`. If the first recovery `t1 <= t0`, REL returns 0 by design.
- OV can auto‑derive critical pairs, but you can configure them in `health.config.json`.

