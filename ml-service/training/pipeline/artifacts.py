import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import yaml

from training.build_feature_reference import sha256_of
from training.pipeline.reporting import KIND_TRAINING_RUN, REPORT_SCHEMA_VERSION

BUNDLE_SCHEMA_VERSION = REPORT_SCHEMA_VERSION


class ArtifactError(RuntimeError):
    pass


class SchemaMismatch(ArtifactError):
    pass


def model_feature_names(model):
    names = getattr(model, "feature_names_in_", None)
    if names is None:
        return None
    return [str(name) for name in names]


def verify_model_schema(model, feature_columns):
    expected = [str(name) for name in feature_columns]
    actual = model_feature_names(model)

    if actual is None:
        raise SchemaMismatch(
            f"Modeli i trajnuar s'ekspozon feature_names_in_ ({len(expected)} features "
            "u pritnin). Artefakti s'do te ishte i vetepershkruar dhe lexuesit do te binin "
            "ne fallback te heshtur. Trajnimi duhet te behet mbi nje DataFrame me emra "
            "kolonash.")

    if actual != expected:
        differing = sum(1 for a, b in zip(actual, expected) if a != b)
        raise SchemaMismatch(
            f"feature_names_in_ i modelit s'perputhet me feature set-in e konfiguruar: "
            f"{len(actual)} kundrejt {len(expected)} features, {differing} pozicione "
            f"ndryshojne.")

    return actual


def verify_saved_schema(paths, bundle, feature_columns):
    expected = [str(name) for name in feature_columns]

    with open(paths["feature_columns"], encoding="utf-8") as handle:
        sidecar = [str(name) for name in json.load(handle)]

    if sidecar != expected:
        raise SchemaMismatch(
            f"{paths['feature_columns'].name} s'perputhet me feature set-in e konfiguruar.")

    if [str(name) for name in bundle["feature_columns"]] != expected:
        raise SchemaMismatch("bundle.feature_columns s'perputhet me feature set-in.")

    if bundle["n_features"] != len(expected):
        raise SchemaMismatch(
            f"bundle.n_features={bundle['n_features']} kundrejt {len(expected)} features.")

    return True


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def artifact_paths(models_dir, artifact_name):
    return {
        "model": models_dir / f"{artifact_name}.joblib",
        "label_encoder": models_dir / f"{artifact_name}_label_encoder.joblib",
        "scaler": models_dir / f"{artifact_name}_scaler.joblib",
        "bundle": models_dir / f"{artifact_name}_bundle.json",
        "feature_columns": models_dir / f"{artifact_name}_feature_columns.json",
    }


def guard_overwrite(models_dir, artifact_name, force=False):
    paths = artifact_paths(models_dir, artifact_name)
    existing = [path for key, path in paths.items()
                if key != "scaler" and path.exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise ArtifactError(
            f"Artefaktet ekzistojne dhe s'mbishkruhen: {names}. "
            "Ndrysho output.artifact_name ose kalo --force.")
    return paths


def save_bundle(config, model, label_encoder, scaler, feature_columns, metrics,
                balancing_report, split_description, dataset_metadata, timings,
                model_params, force=False):
    models_dir = config.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    paths = guard_overwrite(models_dir, config.artifact_name, force=force)

    joblib.dump(model, paths["model"])
    joblib.dump(label_encoder, paths["label_encoder"])

    scaler_file = None
    if scaler is not None:
        joblib.dump(scaler, paths["scaler"])
        scaler_file = paths["scaler"].name
    elif paths["scaler"].exists():
        paths["scaler"].unlink()

    with open(paths["feature_columns"], "w", encoding="utf-8") as handle:
        json.dump(list(feature_columns), handle, indent=1)

    generated_at = utc_now()

    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "report_kind": KIND_TRAINING_RUN,
        "generated_at": generated_at,
        "trained_at": generated_at,
        "evaluated_at": generated_at,
        "artifact_sha256": sha256_of(paths["model"]),
        "name": config.name,
        "version": config.version,
        "description": config.description,
        "algorithm": config.model["type"],
        "seed": config.seed,
        "artifact_file": paths["model"].name,
        "label_encoder_file": paths["label_encoder"].name,
        "scaler_file": scaler_file,
        "feature_columns_file": paths["feature_columns"].name,
        "feature_version": config.features["feature_set"],
        "feature_columns": list(feature_columns),
        "n_features": len(feature_columns),
        "label_classes": [str(name) for name in label_encoder.classes_],
        "model_params": model_params,
        "dataset": dataset_metadata,
        "split": split_description,
        "balancing": balancing_report,
        "timings": timings,
        "metrics": metrics,
        "config": config.to_dict(),
        "config_source": str(config.source_path) if config.source_path else None,
    }

    with open(paths["bundle"], "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=1)

    return paths, bundle


def save_reports(config, bundle):
    reports_dir = config.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = reports_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=1)

    config_path = reports_dir / "config.resolved.yaml"
    with open(config_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config.to_dict(), handle, sort_keys=False, allow_unicode=True)

    return {"metrics": metrics_path, "config": config_path}


def load_bundle(models_dir, artifact_name):
    path = artifact_paths(Path(models_dir), artifact_name)["bundle"]
    if not path.exists():
        raise ArtifactError(f"Bundle s'u gjet: {path}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
