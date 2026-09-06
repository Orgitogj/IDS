import json
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import temporal

TEMPORAL_REPORTS = _ML_SERVICE_ROOT / "reports" / "temporal_evaluation"
RANDOM_REPORTS = _ML_SERVICE_ROOT / "reports" / "artifact_evaluation"

LABELS = {
    "xgb_baseline_temporal_v1": "XGB baseline",
    "xgb_smote_temporal_v1": "XGB balanced",
    "rf_baseline_temporal_v1": "RF baseline",
    "rf_smote_temporal_v1": "RF balanced",
    "mlp_smote_temporal_v1": "MLP balanced",
    "xgb_smote_top50_temporal_v1": "XGB top50",
}

ORDER = ["xgb_baseline_temporal_v1", "xgb_smote_temporal_v1",
         "rf_baseline_temporal_v1", "rf_smote_temporal_v1",
         "mlp_smote_temporal_v1", "xgb_smote_top50_temporal_v1"]


def load_temporal():
    with open(TEMPORAL_REPORTS / "index.json", encoding="utf-8") as handle:
        index = json.load(handle)

    reports = {}
    for stem in index["models"]:
        path = TEMPORAL_REPORTS / stem / "metrics.json"
        with open(path, encoding="utf-8") as handle:
            reports[stem] = json.load(handle)
    return index, reports


def load_random():
    path = RANDOM_REPORTS / "index.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        index = json.load(handle)

    reports = {}
    for record in index["artifacts"]:
        if not record.get("evaluated"):
            continue
        report_path = RANDOM_REPORTS / record["report_dir"] / "metrics.json"
        if report_path.exists():
            with open(report_path, encoding="utf-8") as handle:
                reports[record["artifact"]] = json.load(handle)
    return reports


def main() -> int:
    index, temporal_reports = load_temporal()
    random_reports = load_random()

    split = index["split"]
    print("=" * 120)
    print("A. TEMPORAL PROTOCOL")
    print("=" * 120)
    print(f"  strategy            : {split['strategy']} (protocol {index['protocol_version']})")
    print(f"  boundary            : {split['boundary_timestamp']}")
    print(f"  train period        : {split['train_first_timestamp']} .. "
          f"{split['train_last_timestamp']}")
    print(f"  test period         : {split['test_first_timestamp']} .. "
          f"{split['test_last_timestamp']}")
    print(f"  train / test rows   : {split['train_rows']:,} / {split['test_rows']:,}")

    first = temporal_reports[ORDER[0]] if ORDER[0] in temporal_reports else \
        next(iter(temporal_reports.values()))
    sets = first["metrics"]["class_sets"]
    unseen = first["metrics"]["unseen"]
    print(f"  train classes       : {len(sets[temporal.CLASS_SET_UNION]) - len(sets['classes_only_in_test'])}")
    print(f"  test classes        : {len(sets[temporal.CLASS_SET_TEST])} "
          f"{sets[temporal.CLASS_SET_TEST]}")
    print(f"  seen in both        : {sets[temporal.CLASS_SET_SEEN]}")
    print(f"  UNSEEN in training  : {unseen['unseen_test_classes']} = "
          f"{unseen['unseen_test_rows']:,} rows "
          f"({unseen['unseen_fraction_of_test']:.1%} of the test set)")

    print()
    print("=" * 120)
    print("E. TEMPORAL RESULTS  (strict = all test classes incl. unseen; "
          "seen = classes present in both partitions)")
    print("=" * 120)
    print(f"{'model':<16}{'strict MF1':>12}{'seen MF1':>10}{'strict acc':>12}"
          f"{'seen acc':>10}{'macroP':>9}{'macroR':>9}{'benFPR':>9}{'unseen%':>9}")
    for stem in ORDER:
        if stem not in temporal_reports:
            continue
        metrics = temporal_reports[stem]["metrics"]
        strict = metrics["metrics_by_class_set"][temporal.CLASS_SET_TEST]
        seen = metrics["metrics_by_class_set"][temporal.CLASS_SET_SEEN]
        print(f"{LABELS[stem]:<16}{strict['macro_f1']:>12.6f}{seen['macro_f1']:>10.6f}"
              f"{metrics['overall_accuracy']:>12.6f}"
              f"{(seen['accuracy_over_these_classes'] or 0):>10.6f}"
              f"{strict['macro_precision']:>9.4f}{strict['macro_recall']:>9.4f}"
              f"{(metrics['benign_false_positive_rate'] or 0):>9.5f}"
              f"{metrics['unseen']['unseen_fraction_of_test']:>9.1%}")

    print()
    print("=" * 120)
    print("F. RANDOM-v2 vs TEMPORAL")
    print("=" * 120)
    print(f"{'model':<16}{'rand MF1':>10}{'strict MF1':>12}{'abs D':>10}{'rel %':>9}"
          f"{'rand mR':>9}{'temp mR':>9}{'rand FPR':>10}{'temp FPR':>10}{'seen MF1':>10}")
    for stem in ORDER:
        if stem not in temporal_reports:
            continue
        counterpart = index["models"][stem].get("random_counterpart")
        if counterpart not in random_reports:
            print(f"{LABELS[stem]:<16}  (no random counterpart)")
            continue

        rand = random_reports[counterpart]["metrics"]
        metrics = temporal_reports[stem]["metrics"]
        strict = metrics["metrics_by_class_set"][temporal.CLASS_SET_TEST]
        seen = metrics["metrics_by_class_set"][temporal.CLASS_SET_SEEN]

        rand_f1 = rand["overall"]["macro_f1"]
        delta = strict["macro_f1"] - rand_f1
        print(f"{LABELS[stem]:<16}{rand_f1:>10.6f}{strict['macro_f1']:>12.6f}"
              f"{delta:>+10.6f}{delta / rand_f1 * 100:>+8.1f}%"
              f"{rand['overall']['macro_recall']:>9.4f}"
              f"{strict['macro_recall']:>9.4f}"
              f"{rand['overall']['binary_benign_vs_attack']['benign_false_positive_rate']:>10.5f}"
              f"{(metrics['benign_false_positive_rate'] or 0):>10.5f}"
              f"{seen['macro_f1']:>10.6f}")

    print()
    print("=" * 120)
    print("G. PER-CLASS  (temporal F1 vs random-v2 F1 for the same model)")
    print("=" * 120)
    for stem in ORDER:
        if stem not in temporal_reports:
            continue
        counterpart = index["models"][stem].get("random_counterpart")
        metrics = temporal_reports[stem]["metrics"]
        rand = random_reports.get(counterpart, {}).get("metrics", {}).get("per_class", {})
        test_classes = metrics["class_sets"][temporal.CLASS_SET_TEST]
        train_classes = set(temporal_reports[stem]["train_classes"])

        print(f"\n  {LABELS[stem]} ({temporal_reports[stem]['name']})")
        print(f"    {'class':<28}{'test sup':>10}{'temp F1':>10}{'rand F1':>10}"
              f"{'D F1':>10}  status")
        for name in test_classes:
            row = metrics["per_class"][name]
            temp_f1 = row["f1"]
            rand_f1 = rand.get(name, {}).get("f1")
            delta = (temp_f1 - rand_f1) if rand_f1 is not None else None
            if name not in train_classes:
                status = "UNSEEN in temporal training"
            elif row["support"] < 100:
                status = "low support - no strong claim"
            elif delta is not None and delta < -0.30:
                status = "collapse"
            elif delta is not None and delta < -0.05:
                status = "moderate degradation"
            else:
                status = "stable"
            rand_text = f"{rand_f1:>10.4f}" if rand_f1 is not None else f"{'n/a':>10}"
            delta_text = f"{delta:>+10.4f}" if delta is not None else f"{'n/a':>10}"
            print(f"    {name:<28}{row['support']:>10,}{temp_f1:>10.4f}{rand_text}"
                  f"{delta_text}  {status}")

    print()
    print("=" * 120)
    print("H. UNSEEN-CLASS DECOMPOSITION")
    print("=" * 120)
    for stem in ORDER:
        if stem not in temporal_reports:
            continue
        metrics = temporal_reports[stem]["metrics"]
        unseen = metrics["unseen"]
        strict = metrics["metrics_by_class_set"][temporal.CLASS_SET_TEST]["macro_f1"]
        seen = metrics["metrics_by_class_set"][temporal.CLASS_SET_SEEN]["macro_f1"]
        print(f"  {LABELS[stem]:<16} strict {strict:.6f} -> seen-only {seen:.6f}  "
              f"(gap {seen - strict:+.6f} attributable to {unseen['n_unseen_test_classes']} "
              f"unseen classes covering {unseen['unseen_fraction_of_test']:.1%} of test)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
