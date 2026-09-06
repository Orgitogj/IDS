# Training pipeline (P0-1)

A reproducible replacement for the training logic that previously existed only inside
`notebooks/eda_step1_read.py.ipynb`. The notebook is **kept untouched** as the historical
research record; this package is what you run when a result has to be reproducible.

The training pipeline itself never writes to PostgreSQL. Experiment registration is a
separate, opt-in step — see **Experiment registration (P0-2)** at the end of this file.

---

## Running

```bash
cd ml-service

# smoke test: stratified subsample, no full training
python -m training.train training/configs/xgb_smote_v2.yaml --sample-rows 120000 \
    --name xgb-smote-smoke --artifact-name xgb_smote_smoke \
    --reports-dir reports/training_smoke

# evaluate without writing any artifact
python -m training.train training/configs/xgb_smote_v2.yaml --no-save

# full run
python -m training.train training/configs/xgb_smote_v2.yaml
```

| Flag | Meaning |
|---|---|
| `--sample-rows N` | Stratified subsample with a per-class floor. Recorded as `dataset.subsampled = true`; **metrics from such a run are a smoke test, not a result.** |
| `--min-class-rows N` | Per-class floor for `--sample-rows` (default 10) so rare classes survive the split and SMOTE. |
| `--seed N` | Overrides `seed`. |
| `--no-save` | Evaluate and report, write no artifact. |
| `--force` | Allow overwriting existing artifacts. Off by default, so `v1` cannot be clobbered. |
| `--name`, `--artifact-name`, `--models-dir`, `--reports-dir` | Override the config. |

---

## Stages

`training/pipeline/runner.py` runs seven stages in order:

| # | Stage | Module | Notes |
|---|---|---|---|
| 1 | Load + clean | `data.py` | Reads the cleaned parquet; labels normalised through `evaluate._clean_label` (repairs the latin-1 `\x96` en-dash). |
| 2 | Split | `splitting.py` | Reuses the split functions in `training/evaluate.py`. Disjointness is asserted, not assumed. |
| 3 | Balance | `balancing.py` | **Training rows only.** See below. |
| 4 | Scale | `models.py` | `StandardScaler` fitted on the balanced *training* matrix only; test is transformed, never re-fitted. Only the MLP asks for one. |
| 5 | Train | `models.py` | Model factory; the single `seed` is injected as `random_state`. |
| 6 | Evaluate | `evaluation.py` | Reuses the metric functions in `training/evaluate.py`, so the numbers are computed by the same code that produced `EVALUATION.md`. |
| 7 | Save | `artifacts.py` | Artifact bundle + reports. |

No metric is ever written by hand: every number in `metrics.json` is computed from the
confusion matrix or from `sklearn` at run time.

---

## The balancing recipe

The notebook built `X_train_balanced` in a cell that was lost to re-execution — the
variable is *used* in cells 26, 29, 55, 61 and 72 and *assigned* nowhere. The registered
metadata only carried the string `undersample_benign_200k_oversample_rare_2k`.

The recipe was recovered from the artifacts themselves and is now implemented in
`balancing.py`:

* `BENIGN` is undersampled to at most `benign_cap` (200,000).
* Any non-BENIGN class below `rare_class_min` (2,000) is raised to exactly that with SMOTE.
* Every other class keeps its natural training count.
* Applied to **training rows only**; the test set is never read, resampled or reweighted.

### Evidence that this is the original recipe

| Source | Quantity | Value |
|---|---|---|
| `rf_smote_cicids2017_v1.joblib` | `tree_.weighted_n_node_samples[0]` (bootstrap size = training rows) | **653,897** |
| `rf_baseline_cicids2017_v1.joblib` | same | 2,262,300 = 80 % of 2,827,876 |
| `xgb_smote_cicids2017_v1.joblib` | root `Cover` = `n · 2p(1−p)`, `p = 1/15` | 81,373.9 (predicted 81,373.8) |
| `xgb_baseline_cicids2017_v1.joblib` | same | 281,530.7 (predicted 281,530.7) |
| This pipeline | executed `rows_after` | **653,897** |

Two independent artifacts agree, and the pipeline reproduces the count exactly. The
invariant is pinned by `tests/test_training_pipeline.py::TestAgainstTheRealDataset`.

### What was *not* recovered

The RNG seeds the notebook used for the BENIGN undersample and for SMOTE. Those choose
*which* 200,000 BENIGN rows are kept and *which* synthetic neighbours are generated
(8,652 synthetic rows, 1.3 % of the balanced set). They are unrecoverable, so **models
produced by this pipeline will not be bit-identical to the `v1` artifacts**. The recipe is
reproducible from this version onward; the historical artifacts are not.

---

## Configuration

One YAML per experiment in `training/configs/`. Full schema with defaults lives in
`training/pipeline/config.py`.

```yaml
name: xgb-smote-cicids2017-v2
version: "2.0"
seed: 42                              # propagated to split, undersample, SMOTE, model
dataset:
  path: datasets/cicids2017_cleaned.parquet
features:
  reference: reports/training_feature_reference.json
  feature_set: cicids2017-78-v1       # or: columns: [...] for an explicit list
split:
  strategy: random                    # random | temporal_global | temporal_per_class
  test_size: 0.2
balancing:
  enabled: true
  benign_label: BENIGN
  benign_cap: 200000
  rare_class_min: 2000
  oversampler: smote                  # smote | none
  smote_k_neighbors: 5
model:
  type: xgboost                       # xgboost | random_forest | mlp
  params: {n_estimators: 100, tree_method: hist}
output:
  artifact_name: xgb_smote_cicids2017_v2
```

Shipped configs:

| File | Purpose |
|---|---|
| `xgb_smote_v2.yaml` | The main model: the recovered recipe on all 78 features. |
| `xgb_baseline_v2.yaml` | Same split and hyperparameters, balancing off — isolates the effect of balancing. |
| `rf_smote_v2.yaml` | Same split and balancing, Random Forest — isolates the effect of the algorithm. |
| `mlp_smote_v2.yaml` | The only config that needs a scaler. |
| `xgb_smote_top50_v2.yaml` | The top-50 feature set the live agent uses. |

`IsolationForest` is deliberately rejected by the config validator: it has its own
leak-free, calibrated pipeline in `training/build_anomaly_detector.py`.

---

## Output

Artifacts in `models/` (existing files are never overwritten without `--force`):

```
<artifact_name>.joblib                    the model
<artifact_name>_label_encoder.joblib      fitted on training labels only
<artifact_name>_scaler.joblib             only when the model needs one
<artifact_name>_feature_columns.json      feature names in training order
<artifact_name>_bundle.json               everything needed to reload and audit the run
```

Reports in `reports/training/<name>/`:

```
metrics.json               the bundle, including every metric
config.resolved.yaml       the fully resolved config after defaults
confusion_matrix.csv
confusion_matrix.png
```

`*_bundle.json` records the dataset sha256, the resolved config, the split description
with per-class support, the full balancing report (plan, before/after counts, synthetic
row count, k_neighbors, seed), timings, and the complete metric set.

### Metrics computed

Accuracy, macro precision / recall / F1, weighted F1, per-class precision / recall / F1 /
FPR / FNR / support, the confusion matrix, binary BENIGN-vs-attack recall and false
positive rate, training time, and latency. Latency uses the notebook's methodology —
batch `predict` over the test set divided by row count — and additionally reports
single-flow latency (mean / median / p95) over a random sample, which is the more
meaningful figure for an online IDS.

Classes below `MIN_SUPPORT_FOR_CLAIM` (100 rows) are flagged
`insufficient_support` in the report. Heartbleed (2 test rows), SQL Injection (4) and
Infiltration (7) can never support a performance claim on this dataset.

---

## Leakage guarantees

Each is enforced in code and covered by a test in `tests/test_training_pipeline.py`:

* The split happens before any resampling, and `assert_disjoint` fails the run otherwise.
* `balance_training_set` receives only `train_idx` and never indexes test rows.
* The scaler is fitted on the balanced training matrix; a test asserts the row count it
  sees equals the balanced training size.
* The label encoder is fitted on training labels only.
* Feature sets are fixed lists read from `training_feature_reference.json`; no selection
  step learns anything from the test set.
* A test asserts the source feature matrix is byte-identical after a full run.

---

## Experiment registration (P0-2)

Metrics reach `experiment_results` by exactly one path:

```
model artifact
  → training/evaluate_artifacts.py        recompute on the historical split
  → reports/artifact_evaluation/<name>/metrics.json
  → EvaluationReport.from_path(...)       schema + integrity validation
  → registration.experiment_payload(...)  the only payload builder
  → spring_client.create_experiment_result(payload)
```

```bash
python -m training.evaluate_artifacts                  # audit + recompute every artifact
python -m training.reregister_experiments              # dry run (default)
python -m training.reregister_experiments --commit -y  # actually writes
```

`--dry-run` is the default and `--commit` additionally requires `--yes`. A dry run touches
neither the network nor the database, which is pinned by a test that makes
`requests.request` raise.

### Why manual metrics are impossible now

* `spring_client.record_experiment_result(accuracy=..., f1=...)` raises
  `NotImplementedError` pointing at the report path.
* `create_experiment_result(payload)` rejects any payload whose `notes` do not begin with
  `provenance=`, and any payload carrying unknown fields.
* `experiment_payload` accepts only a validated `EvaluationReport` — a plain dict raises.

### What validation rejects

Missing required fields, an unknown `schema_version` or `report_kind`, a missing artifact
SHA-256, metrics outside `[0, 1]`, non-numeric metrics, per-class supports that do not sum
to `overall.rows`, a macro F1 that disagrees with the report's own confusion matrix, an
accuracy that disagrees with the sklearn cross-check, and latency without a documented
methodology.

At registration time the artifact on disk is re-hashed and compared with the hash in the
report. A mismatch blocks the write unless `--allow-hash-mismatch` is passed explicitly.

### Provenance

The DB schema was **not** migrated. What `experiment_results` has columns for is written to
those columns; everything else goes into `notes` as a `provenance={...}` JSON block:
experiment name, artifact file and SHA-256, model version, algorithm, dataset and its
SHA-256, feature set, split strategy and test size, seed, balancing strategy and resulting
row count, hyperparameters, timestamps, config source, the metrics report path and its
SHA-256, the latency methodology, and both latency figures.

Recomputed rows also carry `historical_stored_values` and `historical_hardcoded_fields`, so
a row that supersedes a hand-entered result records what it superseded. Registration only
inserts; nothing is updated or deleted.
