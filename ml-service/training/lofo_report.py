import json
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import families

REPORTS = _ML_SERVICE_ROOT / "reports" / "lofo_evaluation"

MODEL_LABELS = {
    "xgb_baseline": "XGB baseline",
    "xgb_balanced": "XGB balanced",
    "rf_baseline": "RF baseline",
    "rf_balanced": "RF balanced",
}
MODEL_ORDER = ["xgb_baseline", "xgb_balanced", "rf_baseline", "rf_balanced"]


def load_folds():
    folds = {}
    for path in sorted(REPORTS.glob("lofo_*/metrics.json")):
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        folds[(payload["held_out_family"], payload["model_key"])] = payload
    return folds


def main() -> int:
    folds = load_folds()
    if not folds:
        print("Asnje fold LOFO s'u gjet.", file=sys.stderr)
        return 1

    present_families = sorted({key[0] for key in folds})
    present_models = [m for m in MODEL_ORDER if any(k[1] == m for k in folds)]

    by_family_support = {}
    for family in present_families:
        any_fold = next(folds[k] for k in folds if k[0] == family)
        by_family_support[family] = any_fold["held_out_family_test_support"]

    ordered = sorted(present_families, key=lambda f: min(
        (folds[(f, m)]["metrics"]["detection"].get("attack_detection_rate", 1.0)
         for m in present_models if (f, m) in folds), default=1.0))

    print("=" * 132)
    print("G. AGGREGATE LOFO TABLE  (one row per model x held-out family)")
    print("=" * 132)
    print(f"{'family':<14}{'support':>9}{'tier':<13}{'model':<15}"
          f"{'detect':>8}{'miss':>8}{'knownMF1':>10}{'matched':>9}{'dMF1':>9}"
          f"{'binF1':>8}{'benFPR':>9}  dominant attribution")
    for family in ordered:
        support = by_family_support[family]
        tier = families.support_tier(support)
        for model_key in present_models:
            fold = folds.get((family, model_key))
            if not fold:
                continue
            metrics = fold["metrics"]
            detection = metrics["detection"]
            known = metrics["known_class"]
            binary = metrics["binary"]
            attribution = metrics["attribution"]
            matched = fold.get("matched_random_v2_baseline") or {}
            matched_f1 = matched.get("macro_f1")
            delta = (known.get("macro_f1") - matched_f1) if matched_f1 is not None else None
            dominant = attribution.get("dominant_predicted_label") or "-"
            share = attribution.get("dominant_predicted_label_share")
            dominant_text = f"{dominant}" + (f" ({share:.0%})" if share else "")
            print(f"{family:<14}{support:>9,}{tier:<13}{MODEL_LABELS[model_key]:<15}"
                  f"{detection.get('attack_detection_rate', 0):>8.4f}"
                  f"{detection.get('attack_miss_rate', 0):>8.4f}"
                  f"{known.get('macro_f1', 0):>10.4f}"
                  f"{(matched_f1 if matched_f1 is not None else 0):>9.4f}"
                  f"{(delta if delta is not None else 0):>+9.4f}"
                  f"{binary.get('attack_f1', 0):>8.4f}"
                  f"{(binary.get('benign_false_positive_rate') or 0):>9.5f}  {dominant_text}")

    print()
    print("=" * 132)
    print("H. FAMILY SUMMARY  (sorted by lowest held-out detection rate)")
    print("=" * 132)
    header = f"{'family':<14}{'support':>9}{'tier':<13}"
    for model_key in present_models:
        header += f"{MODEL_LABELS[model_key]:>15}"
    header += f"{'mean':>8}{'median':>8}{'range':>16}  dominant misclassification"
    print(header)

    for family in ordered:
        rates = []
        row = f"{family:<14}{by_family_support[family]:>9,}" \
              f"{families.support_tier(by_family_support[family]):<13}"
        for model_key in present_models:
            fold = folds.get((family, model_key))
            if fold:
                rate = fold["metrics"]["detection"].get("attack_detection_rate")
                rates.append(rate)
                row += f"{rate:>15.4f}"
            else:
                row += f"{'-':>15}"

        if rates:
            mean = sum(rates) / len(rates)
            ordered_rates = sorted(rates)
            middle = len(ordered_rates) // 2
            median = (ordered_rates[middle] if len(ordered_rates) % 2
                      else (ordered_rates[middle - 1] + ordered_rates[middle]) / 2)
            row += f"{mean:>8.4f}{median:>8.4f}"
            row += f"{f'{min(rates):.4f}-{max(rates):.4f}':>16}"

        dominants = {}
        for model_key in present_models:
            fold = folds.get((family, model_key))
            if not fold:
                continue
            label = fold["metrics"]["attribution"].get("dominant_predicted_label")
            if label:
                dominants[label] = dominants.get(label, 0) + 1
        if dominants:
            top = max(dominants.items(), key=lambda item: item[1])
            row += f"  {top[0]} ({top[1]}/{len(rates)} models)"
        else:
            row += "  nothing flagged"
        print(row)

    print()
    print("=" * 132)
    print("I. ATTRIBUTION DETAIL  (where flagged held-out traffic was sent)")
    print("=" * 132)
    for family in ordered:
        print(f"\n  {family} (held-out support {by_family_support[family]:,})")
        for model_key in present_models:
            fold = folds.get((family, model_key))
            if not fold:
                continue
            attribution = fold["metrics"]["attribution"]
            flagged = attribution.get("attack_predictions", 0)
            if not flagged:
                print(f"    {MODEL_LABELS[model_key]:<15} nothing flagged as attack")
                continue
            top = list(attribution["predicted_label_distribution"].items())[:4]
            spread = ", ".join(f"{name} {count}" for name, count in top)
            print(f"    {MODEL_LABELS[model_key]:<15} {flagged:>6,} flagged | {spread}")

    print()
    print("=" * 132)
    print("J. KNOWN-CLASS STABILITY  vs matched random-v2 subset")
    print("=" * 132)
    print(f"{'family':<14}{'model':<15}{'classes':>9}{'LOFO MF1':>10}"
          f"{'matched MF1':>13}{'delta':>9}{'LOFO acc':>10}{'matched acc':>13}")
    for family in ordered:
        for model_key in present_models:
            fold = folds.get((family, model_key))
            if not fold:
                continue
            known = fold["metrics"]["known_class"]
            matched = fold.get("matched_random_v2_baseline") or {}
            matched_f1 = matched.get("macro_f1")
            delta = (known.get("macro_f1") - matched_f1) if matched_f1 is not None else None
            print(f"{family:<14}{MODEL_LABELS[model_key]:<15}{known.get('n_classes', 0):>9}"
                  f"{known.get('macro_f1', 0):>10.4f}"
                  f"{(matched_f1 if matched_f1 is not None else 0):>13.4f}"
                  f"{(delta if delta is not None else 0):>+9.4f}"
                  f"{known.get('accuracy_over_known_rows', 0):>10.4f}"
                  f"{(matched.get('accuracy_over_known_rows') or 0):>13.4f}")

    payload = {
        "schema_version": 1,
        "experiment_type": "lofo",
        "families": present_families,
        "models": present_models,
        "rows": [
            {
                "family": family,
                "member_labels": folds[(family, model_key)]["member_labels"],
                "test_support": by_family_support[family],
                "support_tier": families.support_tier(by_family_support[family]),
                "model": model_key,
                "attack_detection_rate": folds[(family, model_key)]["metrics"][
                    "detection"].get("attack_detection_rate"),
                "attack_miss_rate": folds[(family, model_key)]["metrics"][
                    "detection"].get("attack_miss_rate"),
                "known_macro_f1": folds[(family, model_key)]["metrics"][
                    "known_class"].get("macro_f1"),
                "matched_random_v2_macro_f1": (
                    folds[(family, model_key)].get("matched_random_v2_baseline") or {}
                ).get("macro_f1"),
                "binary_attack_f1": folds[(family, model_key)]["metrics"]["binary"].get(
                    "attack_f1"),
                "benign_false_positive_rate": folds[(family, model_key)]["metrics"][
                    "binary"].get("benign_false_positive_rate"),
                "dominant_predicted_label": folds[(family, model_key)]["metrics"][
                    "attribution"].get("dominant_predicted_label"),
                "dominant_predicted_family": folds[(family, model_key)]["metrics"][
                    "attribution"].get("dominant_predicted_family"),
            }
            for family in ordered for model_key in present_models
            if (family, model_key) in folds
        ],
    }

    out_path = REPORTS / "aggregate.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
