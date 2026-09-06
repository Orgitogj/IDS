import json
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

REPORTS = _ML_SERVICE_ROOT / "reports" / "artifact_evaluation"

V2_ORDER = [
    "xgb_baseline_cicids2017_v2.joblib",
    "xgb_smote_cicids2017_v2.joblib",
    "rf_baseline_cicids2017_v2.joblib",
    "rf_smote_cicids2017_v2.joblib",
    "mlp_smote_cicids2017_v2.joblib",
    "xgb_smote_top50features_v2.joblib",
    "xgb_smote_top30features_v2.joblib",
    "xgb_smote_top20features_v2.joblib",
    "xgb_smote_top10features_v2.joblib",
]

PAIRS = [
    ("XGB baseline", "xgb_baseline_cicids2017_v1.joblib", "xgb_baseline_cicids2017_v2.joblib"),
    ("XGB balanced", "xgb_smote_cicids2017_v1.joblib", "xgb_smote_cicids2017_v2.joblib"),
    ("RF baseline", "rf_baseline_cicids2017_v1.joblib", "rf_baseline_cicids2017_v2.joblib"),
    ("RF balanced", "rf_smote_cicids2017_v1.joblib", "rf_smote_cicids2017_v2.joblib"),
    ("MLP balanced", "mlp_smote_cicids2017_v1.joblib", "mlp_smote_cicids2017_v2.joblib"),
    ("Top10", "xgb_smote_top10features_v1.joblib", "xgb_smote_top10features_v2.joblib"),
    ("Top20", "xgb_smote_top20features_v1.joblib", "xgb_smote_top20features_v2.joblib"),
    ("Top30", "xgb_smote_top30features_v1.joblib", "xgb_smote_top30features_v2.joblib"),
    ("Top50", "xgb_smote_top50features_v1.joblib", "xgb_smote_top50features_v2.joblib"),
]


def load_index():
    with open(REPORTS / "index.json", encoding="utf-8") as handle:
        return json.load(handle)


def by_artifact(index):
    loaded = {}
    for record in index["artifacts"]:
        if not record.get("evaluated"):
            continue
        path = REPORTS / record["report_dir"] / "metrics.json"
        with open(path, encoding="utf-8") as handle:
            loaded[record["artifact"]] = (record, json.load(handle))
    return loaded


def latency(report):
    timings = report["timings"]
    model = timings["model_inference_latency"]
    return model["batch"], model["single_flow"], (
        timings.get("production_path_inference_latency") or {})


def main() -> int:
    index = load_index()
    data = by_artifact(index)

    print("=" * 118)
    print("D. FINAL CANONICAL v2 TABLE")
    print("=" * 118)
    header = (f"{'registry name':<34}{'ft':>4}{'schema':<22}"
              f"{'MacroF1':>10}{'MF1>=100':>10}{'accuracy':>10}{'macroP':>9}"
              f"{'macroR':>9}{'benFPR':>9}")
    print(header)
    for artifact in V2_ORDER:
        if artifact not in data:
            print(f"  MISSING: {artifact}")
            continue
        record, report = data[artifact]
        overall = report["metrics"]["overall"]
        print(f"{record['registry_name']:<34}{record['n_features']:>4}"
              f"{record['feature_schema']:<22}"
              f"{overall['macro_f1']:>10.6f}"
              f"{report['metrics']['macro_f1_min_support']:>10.6f}"
              f"{overall['accuracy']:>10.6f}{overall['macro_precision']:>9.4f}"
              f"{overall['macro_recall']:>9.4f}"
              f"{overall['binary_benign_vs_attack']['benign_false_positive_rate']:>9.5f}")

    print()
    print(f"{'registry name':<34}{'batch ms/flow':>14}{'flows/sec':>12}"
          f"{'sf mean':>9}{'sf med':>9}{'sf p95':>9}{'prod mean':>11}")
    for artifact in V2_ORDER:
        if artifact not in data:
            continue
        record, report = data[artifact]
        batch, single, production = latency(report)
        print(f"{record['registry_name']:<34}{batch['ms_per_flow']:>14.6f}"
              f"{batch['flows_per_second']:>12,.0f}{single['mean_ms']:>9.4f}"
              f"{single['median_ms']:>9.4f}{single['p95_ms']:>9.4f}"
              f"{(production.get('mean_ms') or 0):>11.3f}")

    print()
    print(f"{'registry name':<34}{'artifact':<40}{'sha256'}")
    for artifact in V2_ORDER:
        if artifact not in data:
            continue
        record, _ = data[artifact]
        print(f"{record['registry_name']:<34}{artifact:<40}{record['artifact_sha256']}")

    print()
    print("=" * 118)
    print("E. v1 -> v2 COMPARISON (same split, same uniform harness)")
    print("=" * 118)
    print(f"{'model':<15}{'metric':<12}{'v1':>11}{'v2':>11}{'abs diff':>11}{'rel %':>9}")
    for label, old, new in PAIRS:
        if old not in data or new not in data:
            print(f"{label:<15}  (one side missing)")
            continue
        o1 = data[old][1]["metrics"]
        o2 = data[new][1]["metrics"]
        rows = [("MacroF1", o1["overall"]["macro_f1"], o2["overall"]["macro_f1"]),
                ("MF1>=100", o1["macro_f1_min_support"], o2["macro_f1_min_support"]),
                ("accuracy", o1["overall"]["accuracy"], o2["overall"]["accuracy"])]
        for index, (key, a, b) in enumerate(rows):
            name = label if index == 0 else ""
            print(f"{name:<15}{key:<12}{a:>11.6f}{b:>11.6f}{b - a:>+11.6f}"
                  f"{(b - a) / a * 100:>+8.2f}%")

    print()
    print("PER-CLASS (best model by MacroF1 among v2)")
    best = max((a for a in V2_ORDER if a in data),
               key=lambda a: data[a][1]["metrics"]["overall"]["macro_f1"])
    record, report = data[best]
    print(f"  {record['registry_name']}")
    print(f"  {'class':<28}{'support':>9}{'prec':>9}{'recall':>9}{'F1':>9}{'FPR':>10}")
    for name, row in report["metrics"]["per_class"].items():
        flag = "  <- n<100" if row["support"] < 100 else ""
        precision = row["precision"] if row["precision"] is not None else float("nan")
        print(f"  {name:<28}{row['support']:>9,}{precision:>9.4f}"
              f"{row['recall']:>9.4f}{row['f1']:>9.4f}{row['fpr']:>10.5f}{flag}")

    print()
    print("COLLISION CHECK")
    names = [record["registry_name"] for record, _ in data.values()]
    dirs = [record["report_dir"] for record, _ in data.values()]
    print(f"  evaluated artifacts        : {len(data)}")
    print(f"  unique registry names      : {len(set(names))}  "
          f"{'OK' if len(names) == len(set(names)) else 'COLLISION'}")
    print(f"  unique report directories  : {len(set(dirs))}  "
          f"{'OK' if len(dirs) == len(set(dirs)) else 'COLLISION'}")
    for artifact in ("rf_baseline_cicids2017_v1.joblib", "rf_baseline_cicids2017_v2.joblib"):
        if artifact in data:
            record, _ = data[artifact]
            print(f"  {artifact:<38}{record['version_tag']}  "
                  f"{record['registry_name']:<34}-> {record['report_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
