from scripts.pedr_benchmark_regression import compare_metrics


def test_compare_metrics_regression_triggers() -> None:
    current = {"precision_at_k": 0.4, "recall_at_k": 0.5, "ndcg_at_k": 0.80}
    baseline = {"precision_at_k": 0.4, "recall_at_k": 0.5, "ndcg_at_k": 0.90}
    comparison = compare_metrics(current=current, baseline=baseline, threshold=0.05)
    assert comparison["regression_alert"] is True


def test_compare_metrics_regression_clear() -> None:
    current = {"precision_at_k": 0.4, "recall_at_k": 0.5, "ndcg_at_k": 0.88}
    baseline = {"precision_at_k": 0.4, "recall_at_k": 0.5, "ndcg_at_k": 0.90}
    comparison = compare_metrics(current=current, baseline=baseline, threshold=0.05)
    assert comparison["regression_alert"] is False
