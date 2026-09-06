import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.build_feature_reference import sha256_of

DEFAULT_MODELS_DIR = "models"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_OUT = "reports/feature_ranking_v2.json"

DEFAULT_SOURCE_ARTIFACT = "xgb_smote_cicids2017_v2.joblib"
DEFAULT_TOP_N = [10, 20, 30, 50]
FULL_SET_SUFFIX = "78"

RANKING_METHOD = ("XGBClassifier.feature_importances_ with importance_type unset, which "
                  "is XGBoost's 'gain' default, normalised to sum 1.0. Learned from the "
                  "balanced TRAINING rows only; no test row influences the ranking.")


class RankingError(RuntimeError):
    pass


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


def rank_features(model):
    names = getattr(model, "feature_names_in_", None)
    if names is None:
        raise RankingError(
            "Modeli s'ka feature_names_in_; renditja s'lidhet dot me emrat e features.")

    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        raise RankingError("Modeli s'ka feature_importances_.")

    columns = [str(name) for name in names]
    position = {name: index for index, name in enumerate(columns)}

    ranked = sorted(
        zip(columns, (float(value) for value in importances)),
        key=lambda entry: (-entry[1], position[entry[0]]),
    )

    return [{"rank": index + 1, "feature": name, "importance": value,
             "dataset_position": position[name]}
            for index, (name, value) in enumerate(ranked)]


def build_feature_sets(ranking, base_columns, top_n, version_suffix):
    ordered = [entry["feature"] for entry in ranking]

    sets = {}
    for n in sorted(top_n):
        if n > len(ordered):
            continue
        sets[f"cicids2017-top{n}-{version_suffix}"] = ordered[:n]

    sets[f"cicids2017-{len(base_columns)}-{version_suffix}"] = list(base_columns)
    return sets


def compare_with_previous(new_sets, reference, previous_suffix="v1"):
    previous = reference.get("feature_sets", {})
    overlap = {}

    for name, columns in new_sets.items():
        old_name = name.rsplit("-", 1)[0] + f"-{previous_suffix}"
        old_columns = previous.get(old_name)
        if old_columns is None:
            overlap[name] = {"compared_with": old_name, "available": False}
            continue

        new_set, old_set = set(columns), set(old_columns)
        shared = new_set & old_set
        overlap[name] = {
            "compared_with": old_name,
            "available": True,
            "n_new": len(new_set),
            "n_previous": len(old_set),
            "shared": len(shared),
            "jaccard": len(shared) / len(new_set | old_set) if (new_set | old_set) else None,
            "identical_members": new_set == old_set,
            "identical_order": list(columns) == list(old_columns),
            "only_in_new": sorted(new_set - old_set),
            "only_in_previous": sorted(old_set - new_set),
        }
    return overlap


def build(model, model_path, reference, top_n, version_suffix, seed, source_name):
    base_version = reference["base_feature_version"]
    base_columns = list(reference["feature_sets"][base_version])

    ranking = rank_features(model)
    non_zero = [entry for entry in ranking if entry["importance"] > 0.0]
    feature_sets = build_feature_sets(ranking, base_columns, top_n, version_suffix)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ranking_method": RANKING_METHOD,
        "source_model": source_name,
        "source_artifact": model_path.name,
        "source_artifact_sha256": sha256_of(model_path),
        "seed": seed,
        "version_suffix": version_suffix,
        "n_features": len(ranking),
        "non_zero_importance_count": len(non_zero),
        "zero_importance_features": [entry["feature"] for entry in ranking
                                     if entry["importance"] <= 0.0],
        "zero_importance_warning": (
            f"Only {len(non_zero)} of {len(ranking)} features carry non-zero gain. "
            "Beyond that point the ranking order is arbitrary and additional features "
            "contribute no information to this model."),
        "ranking": ranking,
        "feature_sets": feature_sets,
        "overlap_with_previous": compare_with_previous(feature_sets, reference),
    }


def merge_into_reference(reference, feature_sets):
    updated = dict(reference)
    sets = dict(updated.get("feature_sets", {}))
    added, replaced = [], []

    for name, columns in feature_sets.items():
        if name in sets:
            replaced.append(name)
        else:
            added.append(name)
        sets[name] = list(columns)

    updated["feature_sets"] = sets
    return updated, added, replaced


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nxjerr renditjen e features nga modeli v2 dhe regjistron feature "
                    "set-et top-N. Vetem nga te dhenat e trajnimit.")
    parser.add_argument("--artifact", default=DEFAULT_SOURCE_ARTIFACT)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--top-n", type=int, nargs="+", default=DEFAULT_TOP_N)
    parser.add_argument("--version-suffix", default="v2")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source-name", default="xgb-smote-cicids2017-v2")
    parser.add_argument("--write-reference", action="store_true",
                        help="Shkruaj feature set-et e reja ne training_feature_reference.json")
    args = parser.parse_args()

    models_dir = resolve(args.models_dir)
    model_path = models_dir / args.artifact
    if not model_path.exists():
        print(f"Artefakti s'u gjet: {model_path}\n"
              "Trajno fillimisht modelin v2 me 'python -m training.train "
              "training/configs/xgb_smote_v2.yaml'.", file=sys.stderr)
        return 1

    reference_path = resolve(args.reference)
    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)

    try:
        payload = build(joblib.load(model_path), model_path, reference, args.top_n,
                        args.version_suffix, args.seed, args.source_name)
    except RankingError as error:
        print(f"GABIM: {error}", file=sys.stderr)
        return 1

    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"Burimi        : {payload['source_model']} ({payload['source_artifact']})")
    print(f"Features      : {payload['n_features']} | me gain jo-zero: "
          f"{payload['non_zero_importance_count']}")
    print(f"\nTop 10 sipas gain:")
    for entry in payload["ranking"][:10]:
        print(f"  {entry['rank']:>3}. {entry['feature']:<34}{entry['importance']:.6f}")

    print(f"\nFeature set-e te gjeneruara:")
    for name, columns in payload["feature_sets"].items():
        overlap = payload["overlap_with_previous"][name]
        if overlap.get("available"):
            print(f"  {name:<26}{len(columns):>4} features | ndaj {overlap['compared_with']}: "
                  f"{overlap['shared']}/{overlap['n_previous']} te perbashketa, "
                  f"Jaccard {overlap['jaccard']:.3f}, "
                  f"rend identik={overlap['identical_order']}")
        else:
            print(f"  {name:<26}{len(columns):>4} features | s'ka version te meparshem")

    if args.write_reference:
        updated, added, replaced = merge_into_reference(reference, payload["feature_sets"])
        with open(reference_path, "w", encoding="utf-8") as handle:
            json.dump(updated, handle, indent=1)
        print(f"\n{reference_path.name} u perditesua: {len(added)} te reja, "
              f"{len(replaced)} te zevendesuara.")
        if replaced:
            print(f"  te zevendesuara: {', '.join(replaced)}")
    else:
        print(f"\nU ruajt: {out_path}")
        print("Feature set-et NUK u shkruan ne referencen e trajnimit; "
              "kalo --write-reference kur te jesh gati.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
