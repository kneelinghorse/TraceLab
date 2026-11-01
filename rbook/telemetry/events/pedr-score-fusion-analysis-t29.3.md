# PEDR Score Fusion Analysis (T29.3)

Compares legacy multiplicative post-processing (`(1+t)*(1+i)*q`) against the new independent additive fusion (`(1+t+i)*q`) across representative boost ranges.

## Summary

- Samples: 64
- Legacy multiplier range: 0.1000 -> 1.5473
- New multiplier range: 0.1000 -> 1.5210
- Legacy/New ratio range: 1.0000 -> 1.0173
- Mean delta (legacy - new): 0.004978

## Interpretation

- The new formula removes cross-term compounding (`type_boost * intent_boost`).
- This reduces score inflation while preserving monotonic ordering from independent boosts and quality multiplier.
