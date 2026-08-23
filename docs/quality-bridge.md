# Quality bridge

The `QualityEvaluator` consumes `EvaluationContext` and returns structured quality metrics for semantic matching, grounding, JSON/schema validation, and latency. It is offline by default and does not call Dify, FastGPT, or a judge model.

## Release gates

```powershell
.\.venv\Scripts\airt.exe run `
  --config config.dify.yaml `
  --cases cases/dify.yaml `
  --out runs\quality-gate `
  --fail-on-score 90 `
  --fail-on-quality 0.9 `
  --fail-on-latency 2000
```

The command returns exit code 1 when the security risk score is below 90, the quality pass rate is below 90%, or the average quality latency exceeds 2000 ms. If no cases contain a quality specification, quality gates are skipped.
