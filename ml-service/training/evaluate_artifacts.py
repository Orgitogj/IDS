import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.build_feature_reference import sha256_of
from training.evaluate import _clean_label
from training.pipeline import evaluation, historical, splitting
from training.pipeline.data import LoadedDataset, clean_labels
from training.pipeline.reporting import KIND_ARTIFACT_EVALUATION, REPORT_SCHEMA_VERSION

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_MODELS_DIR = "models"
DEFAULT_REPORTS_DIR = "reports/artifact_evaluation"

LABEL_ENCODER = "label_encoder_cicids2017.joblib"
SCALER = "scaler_cicids2017.joblib"

LABELS_AS_STRINGS = "strings"
LABELS_AS_ENCODED = "encoded"

KIND_MULTICLASS = "multiclass"
KIND_ANOMALY = "anomaly"

HISTORICAL_SPLIT = {"strategy": "random", "test_size": 0.2, "seed": 42}

LEGACY_V1_SPECS = [
    {
        "artifact": "rf_baseline_cicids2017_v1.joblib",
        "registry_name": "rf-baseline-cicids2017-v2",
        "algorithm": "RandomForest",
        "feature_version": "cicids2017-78-v1",
        "labels": LABELS_AS_STRINGS,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": None,
    },
    {
        "artifact": "xgb_baseline_cicids2017_v1.joblib",
        "registry_name": "xgb-baseline-cicids2017-v1",
        "algorithm": "XGBoost",
        "feature_version": "cicids2017-78-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": None,
    },
    {
        "artifact": "rf_smote_cicids2017_v1.joblib",
        "registry_name": "rf-smote-cicids2017-v1",
        "algorithm": "RandomForest",
        "feature_version": "cicids2017-78-v1",
        "labels": LABELS_AS_STRINGS,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "xgb_smote_cicids2017_v1.joblib",
        "registry_name": "xgb-smote-cicids2017-v1",
        "algorithm": "XGBoost",
        "feature_version": "cicids2017-78-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "mlp_smote_cicids2017_v1.joblib",
        "registry_name": "mlp-smote-cicids2017-v1",
        "algorithm": "NeuralNetwork",
        "feature_version": "cicids2017-78-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": True,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "xgb_smote_top10features_v1.joblib",
        "registry_name": "xgb-smote-top10features-v1",
        "algorithm": "XGBoost",
        "feature_version": "cicids2017-top10-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "xgb_smote_top20features_v1.joblib",
        "registry_name": "xgb-smote-top20features-v1",
        "algorithm": "XGBoost",
        "feature_version": "cicids2017-top20-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "xgb_smote_top30features_v1.joblib",
        "registry_name": "xgb-smote-top30features-v1",
        "algorithm": "XGBoost",
        "feature_version": "cicids2017-top30-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "xgb_smote_top50features_v1.joblib",
        "registry_name": "xgb-smote-top50features-v1",
        "algorithm": "XGBoost",
        "feature_version": "cicids2017-top50-v1",
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "xgb_smote_top78features_v1.joblib",
        "registry_name": "xgb-smote-top78features-v1",
        "algorithm": "XGBoost",
        "feature_version": None,
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": False,
        "kind": KIND_MULTICLASS,
        "balancing": "undersample_benign_200k_oversample_rare_2k",
    },
    {
        "artifact": "isolation_forest_cicids2017_v1.joblib",
        "registry_name": "isolation-forest-cicids2017-v1",
        "algorithm": "IsolationForest",
        "feature_version": "cicids2017-78-v1",
        "labels": None,
        "needs_scaler": False,
        "kind": KIND_ANOMALY,
        "balancing": None,
        "excluded_reason": "Binary BENIGN-vs-attack anomaly detector. Its accuracy, "
                           "precision, recall and F1 are computed against a two-class "
                           "problem and are not comparable with the 15-class "
                           "classifiers. Evaluated by "
                           "training/evaluate_isolation_forest.py; see EVALUATION.md.",
    },
    {
        "artifact": "isolation_forest_benign_v2.joblib",
        "registry_name": "isolation-forest-benign-v2",
        "algorithm": "IsolationForest",
        "feature_version": "cicids2017-78-v1",
        "labels": None,
        "needs_scaler": False,
        "kind": KIND_ANOMALY,
        "balancing": None,
        "excluded_reason": "Leak-free anomaly detector with its own calibrated "
                           "thresholds. Same non-comparability as v1.",
    },
]

VERSION_V1 = "v1"
VERSION_V2 = "v2"

ALGORITHM_DISPLAY = {
    "xgboost": "XGBoost",
    "random_forest": "RandomForest",
    "mlp": "NeuralNetwork",
}


def spec_from_bundle(bundle):
    balancing = bundle.get("balancing") or {}
    scaler_file = bundle.get("scaler_file")

    return {
        "artifact": bundle["artifact_file"],
        "registry_name": bundle["name"],
        "algorithm": ALGORITHM_DISPLAY.get(bundle.get("algorithm"),
                                           bundle.get("algorithm")),
        "feature_version": bundle.get("feature_version"),
        "labels": LABELS_AS_ENCODED,
        "needs_scaler": bool(scaler_file),
        "kind": KIND_MULTICLASS,
        "balancing": balancing.get("strategy"),
        "label_encoder_file": bundle.get("label_encoder_file"),
        "scaler_file": scaler_file,
        "feature_columns": bundle.get("feature_columns"),
        "version_tag": VERSION_V2,
        "bundle_sha256": bundle.get("artifact_sha256"),
    }


class RegistryCollision(RuntimeError):
    pass


def report_dir_for(spec):
    return Path(spec["artifact"]).stem


def assert_no_collisions(specs):
    by_name = {}
    by_dir = {}

    for spec in specs:
        by_name.setdefault(spec["registry_name"], []).append(spec["artifact"])
        by_dir.setdefault(report_dir_for(spec), []).append(spec["artifact"])

    duplicated = {name: arts for name, arts in by_name.items() if len(arts) > 1}
    if duplicated:
        detail = "; ".join(f"'{name}' <- {', '.join(sorted(arts))}"
                           for name, arts in sorted(duplicated.items()))
        raise RegistryCollision(
            f"Emra regjistri te dyfishuar: {detail}. Dy artefakte s'mund te ndajne te "
            "njejtin emer regjistri - ml_models.name eshte UNIQUE dhe rezultatet do te "
            "mbishkruheshin. Riemerto artefaktin e ri, jo rekordin historik.")

    collided = {name: arts for name, arts in by_dir.items() if len(arts) > 1}
    if collided:
        detail = "; ".join(f"'{name}' <- {', '.join(sorted(arts))}"
                           for name, arts in sorted(collided.items()))
        raise RegistryCollision(f"Dosje raporti te dyfishuara: {detail}.")

    return True


def discover_artifacts(models_dir):
    discovered = {}

    for bundle_path in sorted(Path(models_dir).glob("*_bundle.json")):
        try:
            with open(bundle_path, encoding="utf-8") as handle:
                bundle = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            print(f"  [skip] {bundle_path.name}: {error}", file=sys.stderr)
            continue
        if not bundle.get("artifact_file"):
            continue
        spec = spec_from_bundle(bundle)
        discovered[spec["artifact"]] = spec

    for spec in LEGACY_V1_SPECS:
        if spec["artifact"] in discovered:
            continue
        if not (Path(models_dir) / spec["artifact"]).exists():
            continue
        legacy = dict(spec)
        legacy.setdefault("label_encoder_file", LABEL_ENCODER)
        legacy.setdefault("scaler_file", SCALER if spec["needs_scaler"] else None)
        legacy.setdefault("feature_columns", None)
        legacy["version_tag"] = VERSION_V2 if "_v2" in spec["artifact"] else VERSION_V1
        legacy["bundle_sha256"] = None
        discovered[spec["artifact"]] = legacy

    specs = sorted(discovered.values(),
                   key=lambda entry: (entry["version_tag"], entry["registry_name"],
                                      entry["artifact"]))
    assert_no_collisions(specs)
    return specs


LATENCY_METHODOLOGY = (
    "avg_latency_ms_batch is batch predict over the whole test set divided by the row "
    "count, which is the methodology the notebook used and therefore the only figure "
    "comparable with the historical numbers. single_flow_latency is a separate "
    "measurement over one row at a time and must never be compared against the batch "
    "figure. Both are hardware-dependent and are not a reproducibility check."
)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


def model_feature_columns(model, fallback):
    names = getattr(model, "feature_names_in_", None)
    if names is None:
        return list(fallback), False
    return [str(name) for name in names], True


def decode_predictions(raw, spec, label_encoder):
    if spec["labels"] == LABELS_AS_STRINGS:
        return np.array([_clean_label(value) for value in raw], dtype=object)

    classes = [_clean_label(name) for name in label_encoder.classes_]
    return np.array([classes[int(index)] for index in raw], dtype=object)


def load_companion(models_dir, filename):
    if not filename:
        return None
    path = models_dir / filename
    if not path.exists():
        return None
    return joblib.load(path)


def audit_artifact(spec, models_dir, reference, dataset, test_idx, reports_dir,
                   scaler=None, label_encoder=None, sample_test_rows=None):
    artifact_path = models_dir / spec["artifact"]

    label_encoder = load_companion(models_dir, spec.get("label_encoder_file")) or label_encoder
    spec_scaler = load_companion(models_dir, spec.get("scaler_file"))
    if spec_scaler is not None:
        scaler = spec_scaler

    record = {
        "artifact": spec["artifact"],
        "registry_name": spec["registry_name"],
        "algorithm": spec["algorithm"],
        "version_tag": spec.get("version_tag"),
        "kind": spec["kind"],
        "artifact_exists": artifact_path.exists(),
        "loads": False,
        "feature_schema": None,
        "needs_scaler": spec["needs_scaler"],
        "scaler_available": scaler is not None,
        "evaluated": False,
        "excluded_reason": spec.get("excluded_reason"),
        "issues": [],
    }

    if not artifact_path.exists():
        record["issues"].append("artifact absent from models/")
        return record, None

    record["artifact_sha256"] = sha256_of(artifact_path)
    record["artifact_bytes"] = artifact_path.stat().st_size

    try:
        model = joblib.load(artifact_path)
    except Exception as error:
        record["issues"].append(f"load failed: {error!r}")
        return record, None

    record["loads"] = True
    record["model_class"] = type(model).__name__

    base_columns = reference["feature_sets"]["cicids2017-78-v1"]
    columns, declared = model_feature_columns(model, spec.get("feature_columns")
                                              or base_columns)
    record["n_features"] = len(columns)
    record["carries_feature_names"] = declared

    matched = None
    for version, names in reference["feature_sets"].items():
        if list(names) == columns:
            matched = version
            break
    record["feature_schema"] = matched or f"unregistered-{len(columns)}-features"

    if matched is None:
        record["issues"].append(
            f"feature order matches no registered feature set ({len(columns)} features)")
    elif spec["feature_version"] and matched != spec["feature_version"]:
        record["issues"].append(
            f"expected feature set {spec['feature_version']}, artifact declares {matched}")

    missing = [name for name in columns if name not in dataset.feature_columns]
    if missing:
        record["issues"].append(f"{len(missing)} features absent from the dataset")
        return record, None

    if spec["kind"] == KIND_ANOMALY:
        record["issues"].append("excluded from the multiclass comparison by design")
        return record, None

    if spec["needs_scaler"] and scaler is None:
        record["issues"].append(f"{SCALER} missing; cannot evaluate")
        return record, None

    positions = [dataset.feature_columns.index(name) for name in columns]

    evaluation_idx = test_idx
    if sample_test_rows is not None and sample_test_rows < len(test_idx):
        rng = np.random.default_rng(HISTORICAL_SPLIT["seed"])
        evaluation_idx = np.sort(
            rng.choice(test_idx, size=sample_test_rows, replace=False))

    X_test = dataset.features[np.ix_(evaluation_idx, positions)]
    y_test = dataset.labels[evaluation_idx]

    if spec["needs_scaler"]:
        scaler_columns, _ = model_feature_columns(scaler, base_columns)
        if list(scaler_columns) != list(columns):
            scaler_positions = [dataset.feature_columns.index(name)
                                for name in scaler_columns]
            X_scaled_source = dataset.features[np.ix_(evaluation_idx, scaler_positions)]
        else:
            X_scaled_source = X_test
        X_test = scaler.transform(X_scaled_source)

    raw, batch_timing = evaluation.measure_batch_latency(model, X_test)
    y_pred = decode_predictions(raw, spec, label_encoder)

    run_reports = reports_dir / report_dir_for(spec)
    if run_reports.exists() and (run_reports / "metrics.json").exists():
        existing = json.load(open(run_reports / "metrics.json", encoding="utf-8"))
        if existing.get("artifact_file") not in (None, spec["artifact"]):
            raise RegistryCollision(
                f"{run_reports.name}/metrics.json i perket "
                f"'{existing.get('artifact_file')}', jo '{spec['artifact']}'.")
    run_reports.mkdir(parents=True, exist_ok=True)
    metrics = evaluation.evaluate_predictions(
        y_test, y_pred, run_reports, spec["registry_name"])

    record["evaluated"] = True
    record["sample_size"] = int(len(evaluation_idx))

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_kind": KIND_ARTIFACT_EVALUATION,
        "generated_at": utc_now(),
        "evaluated_at": utc_now(),
        "trained_at": None,
        "name": spec["registry_name"],
        "version": "2.0" if spec.get("version_tag") == VERSION_V2 else "1.0",
        "algorithm": spec["algorithm"],
        "artifact_file": spec["artifact"],
        "artifact_sha256": record["artifact_sha256"],
        "feature_version": record["feature_schema"],
        "feature_columns": columns,
        "n_features": len(columns),
        "label_classes": sorted({str(name) for name in dataset.labels}),
        "model_params": {key: value for key, value in model.get_params().items()
                         if isinstance(value, (int, float, str, bool, type(None)))},
        "dataset": {
            "name": dataset.metadata["name"],
            "sha256": dataset.metadata["sha256"],
            "rows_in_file": dataset.metadata["rows_in_file"],
            "rows_used": dataset.metadata["rows_used"],
            "subsampled": bool(sample_test_rows is not None
                               and sample_test_rows < len(test_idx)),
        },
        "split": {
            "strategy": HISTORICAL_SPLIT["strategy"],
            "test_size": HISTORICAL_SPLIT["test_size"],
            "test_rows": int(len(evaluation_idx)),
            "note": "The historical split the notebook used: stratified "
                    "train_test_split(test_size=0.2, random_state=42). Reproduced here "
                    "so the recomputed numbers are comparable with the stored ones.",
        },
        "seed": HISTORICAL_SPLIT["seed"],
        "balancing": {
            "strategy": spec["balancing"],
            "note": "Declared in the registered metadata of the v1 artifact. The "
                    "training rows themselves are not reproducible for v1; see "
                    "training/README.md.",
        } if spec["balancing"] else None,
        "timings": evaluation.build_timings(
            None, batch_timing,
            evaluation.measure_single_flow_latency(
                model, X_test, seed=HISTORICAL_SPLIT["seed"]),
            evaluation.measure_production_path_latency(
                model, X_test, columns, seed=HISTORICAL_SPLIT["seed"])),
        "metrics": metrics,
        "config_source": "training/evaluate_artifacts.py",
    }

    report_path = run_reports / "metrics.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)

    record["metrics_report"] = str(report_path.relative_to(_ML_SERVICE_ROOT).as_posix())
    record["report_dir"] = run_reports.name
    record["recomputed"] = {
        "accuracy": metrics["overall"]["accuracy"],
        "precisionScore": metrics["overall"]["macro_precision"],
        "recall": metrics["overall"]["macro_recall"],
        "f1Score": metrics["overall"]["macro_f1"],
        "avgLatencyMs": report["timings"]["avg_latency_ms_batch"],
        "sampleSize": record["sample_size"],
    }

    return record, report


def compare_with_stored(record, stored_lookup):
    name = record["registry_name"]
    stored = stored_lookup.get(name)
    if not stored or not record.get("recomputed"):
        return None

    rows = []
    for field in ("accuracy", "precisionScore", "recall", "f1Score", "avgLatencyMs",
                  "sampleSize"):
        stored_value = stored.get(field)
        if isinstance(stored_value, dict):
            origin = stored_value.get("origin")
            stored_value = stored_value.get("value")
        else:
            origin = historical.ORIGIN_UNKNOWN
        recomputed = record["recomputed"].get(field)
        if stored_value is None or recomputed is None:
            continue
        rows.append({
            "field": field,
            "stored": stored_value,
            "recomputed": recomputed,
            "difference": float(recomputed) - float(stored_value),
            "stored_origin": origin,
            "comparable": field != "avgLatencyMs",
        })
    return rows


def fetch_stored_from_backend():
    from app.services import spring_client

    experiments = spring_client._request("GET", "/api/experiments")
    models = spring_client._request("GET", "/api/models")
    by_id = {entry["id"]: entry for entry in models}

    lookup = {}
    for entry in experiments:
        model = by_id.get(entry.get("mlModelId"), {})
        name = entry.get("mlModelName") or model.get("name")
        if not name:
            continue
        lookup[name] = {
            "accuracy": entry.get("accuracy"),
            "precisionScore": entry.get("precisionScore"),
            "recall": entry.get("recall"),
            "f1Score": entry.get("f1Score"),
            "avgLatencyMs": entry.get("avgLatencyMs"),
            "sampleSize": entry.get("sampleSize"),
            "notes": entry.get("notes"),
            "source": "database",
        }
    return lookup


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditon dhe rillogarit metrikat e cdo artefakti te regjistruar.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--only", default=None,
                        help="Vlereso vetem artefaktet emri i te cileve permban kete tekst")
    parser.add_argument("--sample-test-rows", type=int, default=None,
                        help="Vlereso mbi nje nen-mostre te test-it (vetem per shpejtesi; "
                             "rezultatet nuk jane te krahasueshme me ato historike)")
    parser.add_argument("--fetch-stored", action="store_true",
                        help="Lexo vlerat e ruajtura nga backend-i (vetem GET)")
    args = parser.parse_args()

    dataset_path = resolve(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    models_dir = resolve(args.models_dir)
    reports_dir = resolve(args.reports_dir)

    with open(resolve(args.reference), encoding="utf-8") as handle:
        reference = json.load(handle)

    base_columns = list(reference["feature_sets"]["cicids2017-78-v1"])

    print(f"Duke lexuar {dataset_path.name} ({len(base_columns)} features) ...")
    meta = pd.read_parquet(dataset_path, columns=["Label"])
    labels = clean_labels(meta["Label"].to_numpy())
    del meta

    frame = pd.read_parquet(dataset_path, columns=base_columns)
    features = frame[base_columns].to_numpy(dtype="float32")
    del frame

    dataset = LoadedDataset(features, labels, base_columns, metadata={
        "name": dataset_path.name,
        "sha256": sha256_of(dataset_path),
        "rows_in_file": int(len(labels)),
        "rows_used": int(len(labels)),
    })

    train_idx, test_idx = splitting.split_indices(
        dataset, HISTORICAL_SPLIT["strategy"], HISTORICAL_SPLIT["test_size"],
        HISTORICAL_SPLIT["seed"])
    splitting.assert_disjoint(train_idx, test_idx)
    print(f"  {len(labels):,} rreshta | split historik: train {len(train_idx):,} | "
          f"test {len(test_idx):,}")

    label_encoder = None
    encoder_path = models_dir / LABEL_ENCODER
    if encoder_path.exists():
        label_encoder = joblib.load(encoder_path)

    scaler = None
    scaler_path = models_dir / SCALER
    if scaler_path.exists():
        scaler = joblib.load(scaler_path)

    stored_lookup = {name: dict(entry)
                     for name, entry in historical.STORED_RESULTS.items()}
    stored_source = "notebook outputs"

    if args.fetch_stored:
        try:
            fetched = fetch_stored_from_backend()
            stored_lookup.update(fetched)
            stored_source = "database"
            print(f"  {len(fetched)} rezultate te ruajtura u lexuan nga backend-i.")
        except Exception as error:
            print(f"  KUJDES: backend-i s'u arrit ({error}); po perdor vlerat e njohura "
                  "nga output-et e notebook-ut.", file=sys.stderr)

    specs = discover_artifacts(models_dir)
    if args.only:
        specs = [spec for spec in specs if args.only in spec["artifact"]
                 or args.only in spec["registry_name"]]

    records = []
    for spec in specs:
        print(f"\n--- {spec['registry_name']} ({spec['artifact']}) ---")
        record, _ = audit_artifact(
            spec, models_dir, reference, dataset, test_idx, reports_dir,
            scaler, label_encoder, sample_test_rows=args.sample_test_rows)

        record["comparison"] = compare_with_stored(record, stored_lookup)
        records.append(record)

        if not record["artifact_exists"]:
            print("  MUNGON")
            continue
        print(f"  loads={record['loads']} | features={record.get('n_features')} "
              f"({record['feature_schema']}) | scaler={record['needs_scaler']}")
        for issue in record["issues"]:
            print(f"  ! {issue}")
        if record["evaluated"]:
            recomputed = record["recomputed"]
            print(f"  accuracy {recomputed['accuracy']:.6f} | "
                  f"macro P {recomputed['precisionScore']:.6f} | "
                  f"macro R {recomputed['recall']:.6f} | "
                  f"macro F1 {recomputed['f1Score']:.6f}")
            print(f"  batch latency {recomputed['avgLatencyMs']:.6f} ms/flow | "
                  f"n={recomputed['sampleSize']:,}")
        if record["comparison"]:
            print(f"  {'field':<16}{'stored':>16}{'recomputed':>16}{'difference':>16}"
                  f"  origin")
            for row in record["comparison"]:
                marker = "" if row["comparable"] else "  (not comparable: hardware)"
                print(f"  {row['field']:<16}{row['stored']:>16.6f}"
                      f"{row['recomputed']:>16.6f}{row['difference']:>+16.6f}"
                      f"  {row['stored_origin']}{marker}")

    summary = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "dataset": dataset.metadata,
        "split": HISTORICAL_SPLIT,
        "stored_values_source": stored_source,
        "stored_values_caveat": historical.UNRECOVERABLE_OFFLINE,
        "latency_methodology": LATENCY_METHODOLOGY,
        "sample_test_rows": args.sample_test_rows,
        "artifacts": records,
    }

    reports_dir.mkdir(parents=True, exist_ok=True)
    index_path = reports_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1)

    evaluated = sum(1 for record in records if record["evaluated"])
    excluded = sum(1 for record in records if record["kind"] == KIND_ANOMALY)
    print(f"\nU vleresuan {evaluated} klasifikues multiclass, {excluded} detektore "
          f"anomalish u perjashtuan me qellim.")
    print(f"U ruajt: {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
