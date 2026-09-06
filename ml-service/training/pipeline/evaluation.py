import time

import numpy as np
import pandas as pd

from training.evaluate import (
    MIN_SUPPORT_FOR_CLAIM,
    classes_at_min_support,
    confusion_matrix_frame,
    macro_f1_at_min_support,
    macro_f1_from_per_class,
    overall_metrics,
    per_class_metrics,
    save_confusion_matrix_csv,
    save_confusion_matrix_png,
    weighted_f1_from_per_class,
)

BATCH_WARMUP_ROWS = 1000
BATCH_REPETITIONS = 3

SINGLE_FLOW_WARMUP = 20
SINGLE_FLOW_SAMPLES = 200

METRIC_MODEL_INFERENCE = "model_inference_latency"
METRIC_PRODUCTION_PATH = "production_path_inference_latency"

LATENCY_SCOPE = ("model inference only, on a model-input-ready ndarray. Feature "
                 "validation, DataFrame construction and conversion, SHAP, HTTP, "
                 "database and frontend are all outside the timed region. This is NOT "
                 "production latency.")

PRODUCTION_PATH_SCOPE = (
    "Mimics app/ml/inference.predict: build a one-row DataFrame with the model's feature "
    "columns, then predict. DataFrame construction IS inside the timed region. HTTP, "
    "Spring Boot, database, SHAP, LLM and frontend are NOT included - those belong to "
    "end_to_end_IDS_latency, measured separately.")

BATCH_METHODOLOGY = (
    f"Batch throughput: one predict() over the whole test set, after a discarded warm-up "
    f"of {BATCH_WARMUP_ROWS} rows, repeated {BATCH_REPETITIONS} times; the median is "
    f"reported. Comparable with the historical notebook figures. {LATENCY_SCOPE}")

SINGLE_FLOW_METHODOLOGY = (
    f"Single-flow latency: predict() on one row at a time, {SINGLE_FLOW_SAMPLES} rows "
    f"sampled from the test set, after {SINGLE_FLOW_WARMUP} discarded warm-up rows. "
    f"Mean, median and p95 are reported. This is NOT comparable with the batch figure. "
    f"{LATENCY_SCOPE}")


def as_model_input(X):
    return np.asarray(X)


def measure_batch_latency(model, X_test, repetitions=BATCH_REPETITIONS,
                          warmup_rows=BATCH_WARMUP_ROWS):
    rows = len(X_test)
    if not rows:
        return np.array([]), {"metric": METRIC_MODEL_INFERENCE, "batch_size": 0,
                              "ms_per_flow": None}

    X_test = as_model_input(X_test)
    model.predict(X_test[:min(warmup_rows, rows)])

    durations = []
    predictions = None
    for _ in range(max(1, repetitions)):
        started = time.perf_counter()
        predictions = model.predict(X_test)
        durations.append(time.perf_counter() - started)

    median_seconds = float(np.median(durations))

    timing = {
        "metric": METRIC_MODEL_INFERENCE,
        "batch_size": int(rows),
        "warmup_rows": int(min(warmup_rows, rows)),
        "repetitions": int(len(durations)),
        "seconds_per_repetition": [float(value) for value in durations],
        "median_seconds": median_seconds,
        "min_seconds": float(np.min(durations)),
        "max_seconds": float(np.max(durations)),
        "ms_per_flow": median_seconds / rows * 1000.0,
        "flows_per_second": rows / median_seconds if median_seconds else None,
        "methodology": BATCH_METHODOLOGY,
    }

    return predictions, timing


def measure_single_flow_latency(model, X_test, samples=SINGLE_FLOW_SAMPLES,
                                warmup=SINGLE_FLOW_WARMUP, seed=42):
    rows = len(X_test)
    if not rows:
        return None

    X_test = as_model_input(X_test)
    rng = np.random.default_rng(seed)
    picks = rng.choice(rows, size=min(samples, rows), replace=False)

    for index in picks[:min(warmup, len(picks))]:
        model.predict(X_test[index:index + 1])

    durations = []
    for index in picks:
        row = X_test[index:index + 1]
        started = time.perf_counter()
        model.predict(row)
        durations.append((time.perf_counter() - started) * 1000.0)

    return {
        "metric": METRIC_MODEL_INFERENCE,
        "samples": int(len(durations)),
        "warmup": int(min(warmup, len(picks))),
        "mean_ms": float(np.mean(durations)),
        "median_ms": float(np.median(durations)),
        "p95_ms": float(np.percentile(durations, 95)),
        "methodology": SINGLE_FLOW_METHODOLOGY,
    }


def measure_production_path_latency(model, X_test, feature_columns,
                                    samples=SINGLE_FLOW_SAMPLES,
                                    warmup=SINGLE_FLOW_WARMUP, seed=42):
    values = as_model_input(X_test)
    rows = len(values)
    if not rows:
        return None

    columns = [str(name) for name in feature_columns]
    rng = np.random.default_rng(seed)
    picks = rng.choice(rows, size=min(samples, rows), replace=False)

    for index in picks[:min(warmup, len(picks))]:
        model.predict(pd.DataFrame([values[index].tolist()], columns=columns))

    durations = []
    for index in picks:
        vector = values[index].tolist()
        started = time.perf_counter()
        frame = pd.DataFrame([vector], columns=columns)
        model.predict(frame)
        durations.append((time.perf_counter() - started) * 1000.0)

    return {
        "metric": METRIC_PRODUCTION_PATH,
        "samples": int(len(durations)),
        "warmup": int(min(warmup, len(picks))),
        "mean_ms": float(np.mean(durations)),
        "median_ms": float(np.median(durations)),
        "p95_ms": float(np.percentile(durations, 95)),
        "methodology": PRODUCTION_PATH_SCOPE,
    }


def build_timings(train_seconds, batch_timing, single_flow, production_path=None):
    return {
        "train_seconds": float(train_seconds) if train_seconds is not None else None,
        "predict_seconds_batch": batch_timing.get("median_seconds"),
        "avg_latency_ms_batch": batch_timing.get("ms_per_flow"),
        "latency_methodology": BATCH_METHODOLOGY,
        "latency_scope": LATENCY_SCOPE,
        "model_inference_latency": {
            "metric": METRIC_MODEL_INFERENCE,
            "scope": LATENCY_SCOPE,
            "batch": batch_timing,
            "single_flow": single_flow,
        },
        "production_path_inference_latency": production_path,
        "batch_latency": batch_timing,
        "single_flow_latency": single_flow,
    }


def evaluate_predictions(y_true, y_pred, reports_dir, run_name, title=None):
    classes = sorted(set(y_true) | set(y_pred))
    matrix = confusion_matrix_frame(y_true, y_pred, classes)
    per_class = per_class_metrics(matrix)
    overall = overall_metrics(y_true, y_pred, matrix)

    overall["macro_f1_min_support"] = macro_f1_at_min_support(per_class)

    csv_path = save_confusion_matrix_csv(matrix, reports_dir / "confusion_matrix.csv")
    png_path = save_confusion_matrix_png(
        matrix, reports_dir / "confusion_matrix.png",
        title or f"Confusion matrix - {run_name} ({overall['rows']:,} test flows)")

    insufficient = [name for name, row in per_class.items()
                    if not row["sufficient_support"] and row["support"] > 0]
    absent = [name for name, row in per_class.items() if row["support"] == 0]

    return {
        "overall": overall,
        "primary_metric": "macro_f1",
        "sensitivity_metric": "macro_f1_min_support",
        "macro_f1_from_confusion_matrix": macro_f1_from_per_class(per_class),
        "macro_f1_min_support": macro_f1_at_min_support(per_class),
        "classes_in_macro_f1_min_support": classes_at_min_support(per_class),
        "weighted_f1_from_confusion_matrix": weighted_f1_from_per_class(per_class),
        "min_support_for_claim": MIN_SUPPORT_FOR_CLAIM,
        "insufficient_support_classes": insufficient,
        "absent_from_test_classes": absent,
        "per_class": per_class,
        "confusion_matrix_csv": csv_path.name,
        "confusion_matrix_png": png_path.name,
    }


def print_report(run_name, metrics, timings):
    overall = metrics["overall"]
    print(f"\n=== {run_name} ===")
    print(f"  test rows {overall['rows']:,} | accuracy {overall['accuracy']:.4f}")
    restricted = metrics.get("macro_f1_min_support")
    restricted_text = f"{restricted:.4f}" if restricted is not None else "n/a"
    print(f"  macro F1 (PRIMARY, all {len(metrics['per_class'])} classes) "
          f"{overall['macro_f1']:.4f}")
    print(f"  macro F1 (sensitivity, support >= {metrics['min_support_for_claim']}, "
          f"{len(metrics['classes_in_macro_f1_min_support'])} classes) {restricted_text}")
    print(f"  weighted F1 {overall['weighted_f1']:.4f} | macro precision "
          f"{overall['macro_precision']:.4f} | macro recall {overall['macro_recall']:.4f}")

    binary = overall.get("binary_benign_vs_attack")
    if binary and binary["attack_recall"] is not None:
        print(f"  attack recall {binary['attack_recall']:.4f} | "
              f"benign FPR {binary['benign_false_positive_rate']:.4f}")

    if timings.get("train_seconds"):
        print(f"  train {timings['train_seconds']:.1f}s")
    model_latency = timings.get("model_inference_latency") or {}
    batch = model_latency.get("batch") or {}
    if batch.get("ms_per_flow"):
        print(f"  model_inference_latency  batch  {batch['ms_per_flow']:.6f} ms/flow "
              f"({batch.get('flows_per_second', 0):,.0f} flows/s, median of "
              f"{batch.get('repetitions')} reps)")
    single = model_latency.get("single_flow") or {}
    if single:
        print(f"  model_inference_latency  single mean {single['mean_ms']:.4f} | median "
              f"{single['median_ms']:.4f} | p95 {single['p95_ms']:.4f} ms "
              f"(n={single['samples']}) - NOT comparable with batch")
    production = timings.get("production_path_inference_latency") or {}
    if production:
        print(f"  production_path_latency  mean {production['mean_ms']:.4f} | median "
              f"{production['median_ms']:.4f} | p95 {production['p95_ms']:.4f} ms "
              f"(n={production['samples']}) - DataFrame prep + predict, separate metric")

    print(f"  {'class':<28}{'support':>9}{'prec':>8}{'recall':>8}{'F1':>8}{'FPR':>10}{'FNR':>8}")
    for name, row in metrics["per_class"].items():
        if row["support"] == 0:
            flag = "  <- absent from this test set"
        elif not row["sufficient_support"]:
            flag = "  <- insufficient support"
        else:
            flag = ""
        precision = row["precision"] if row["precision"] is not None else float("nan")
        recall = row["recall"] if row["recall"] is not None else float("nan")
        fpr = row["fpr"] if row["fpr"] is not None else float("nan")
        fnr = row["fnr"] if row["fnr"] is not None else float("nan")
        print(f"  {name:<28}{row['support']:>9,}{precision:>8.3f}{recall:>8.3f}"
              f"{row['f1']:>8.3f}{fpr:>10.5f}{fnr:>8.3f}{flag}")
