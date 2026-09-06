import time

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from training.pipeline import artifacts, balancing, data, evaluation, models, splitting

TEMPORAL_STRATEGIES = (splitting.STRATEGY_TEMPORAL_GLOBAL,
                       splitting.STRATEGY_TEMPORAL_PER_CLASS)


class PipelineResult:
    def __init__(self, bundle, paths, report_paths):
        self.bundle = bundle
        self.paths = paths
        self.report_paths = report_paths

    @property
    def metrics(self):
        return self.bundle["metrics"]

    @property
    def balancing(self):
        return self.bundle["balancing"]


def run(config, sample_rows=None, min_class_rows=data.DEFAULT_MIN_CLASS_ROWS,
        force=False, save=True, verbose=True):
    def say(message):
        if verbose:
            print(message)

    feature_columns = data.load_feature_columns(config)
    strategy = config.split["strategy"]
    needs_timestamps = strategy in TEMPORAL_STRATEGIES

    if save:
        config.models_dir.mkdir(parents=True, exist_ok=True)
        artifacts.guard_overwrite(config.models_dir, config.artifact_name, force=force)

    say(f"[1/7] Ngarkim: {config.dataset_path.name} "
        f"({config.features['feature_set']}, {len(feature_columns)} features)")
    dataset = data.load_dataset(config, feature_columns, sample_rows=sample_rows,
                               needs_timestamps=needs_timestamps,
                               min_class_rows=min_class_rows)
    say(f"      {len(dataset):,} rreshta, {len(dataset.class_counts)} klasa"
        + (f"  [SUBSET, jo perfaqesues]" if dataset.metadata["subsampled"] else ""))
    if dataset.metadata["subsampled"]:
        say("      KUJDES: xhirim mbi nen-mostre - metrikat jane smoke test, jo rezultat.")

    say(f"[2/7] Split: {strategy}, test_size={config.split['test_size']}, "
        f"seed={config.seed}")
    train_idx, test_idx = splitting.split_indices(
        dataset, strategy, config.split["test_size"], config.seed)
    splitting.assert_disjoint(train_idx, test_idx)
    split_description = splitting.describe(
        dataset, train_idx, test_idx, strategy, config.split["test_size"])
    say(f"      train {len(train_idx):,} | test {len(test_idx):,} (i paprekur)")

    say(f"[3/7] Balancim (vetem mbi train): {config.balancing}")
    X_train, y_train, balancing_report = balancing.balance_training_set(
        dataset.features, dataset.labels, train_idx, config.balancing, config.seed)
    say(f"      {balancing_report['rows_before']:,} -> {balancing_report['rows_after']:,} "
        f"rreshta ({balancing_report['synthetic_rows']:,} sintetike)")

    X_test = dataset.features[test_idx]
    y_test = dataset.labels[test_idx]

    label_encoder = LabelEncoder()
    y_train_encoded = label_encoder.fit_transform(y_train)

    X_train = pd.DataFrame(X_train, columns=feature_columns)
    X_test = pd.DataFrame(X_test, columns=feature_columns)

    scaler = models.build_scaler(config.model_type)
    if scaler is not None:
        say("[4/7] Scaler: StandardScaler i pershtatur VETEM mbi train")
        X_train = pd.DataFrame(scaler.fit_transform(X_train), columns=feature_columns)
        X_test_scaled = pd.DataFrame(scaler.transform(X_test), columns=feature_columns)
    else:
        say("[4/7] Scaler: nuk nevojitet per kete model")
        X_test_scaled = X_test

    model_params = models.resolve_params(config.model_type, config.model.get("params"))
    model = models.build_model(config.model_type, model_params, config.seed)

    say(f"[5/7] Trajnim: {models.algorithm_name(config.model_type)} mbi "
        f"{len(y_train_encoded):,} rreshta")
    started = time.perf_counter()
    model.fit(X_train, y_train_encoded)
    train_seconds = time.perf_counter() - started
    say(f"      perfundoi ne {train_seconds:.1f}s")

    artifacts.verify_model_schema(model, feature_columns)

    say("[6/7] Vleresim mbi test-in e paprekur")
    encoded_predictions, batch_timing = evaluation.measure_batch_latency(
        model, X_test_scaled)
    y_pred = label_encoder.inverse_transform(encoded_predictions)

    reports_dir = config.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    metrics = evaluation.evaluate_predictions(y_test, y_pred, reports_dir, config.name)

    timings = evaluation.build_timings(
        train_seconds,
        batch_timing,
        evaluation.measure_single_flow_latency(model, X_test_scaled, seed=config.seed),
        evaluation.measure_production_path_latency(
            model, X_test_scaled, feature_columns, seed=config.seed),
    )

    if verbose:
        evaluation.print_report(config.name, metrics, timings)

    if not save:
        bundle = {
            "name": config.name,
            "metrics": metrics,
            "balancing": balancing_report,
            "split": split_description,
            "timings": timings,
            "dataset": dataset.metadata,
            "label_classes": [str(name) for name in label_encoder.classes_],
            "feature_columns": list(feature_columns),
        }
        return PipelineResult(bundle, {}, {})

    say("[7/7] Ruajtje e artefakteve dhe raporteve")
    paths, bundle = artifacts.save_bundle(
        config=config,
        model=model,
        label_encoder=label_encoder,
        scaler=scaler,
        feature_columns=feature_columns,
        metrics=metrics,
        balancing_report=balancing_report,
        split_description=split_description,
        dataset_metadata=dataset.metadata,
        timings=timings,
        model_params=models.serialisable_params(model_params, config.seed),
        force=force,
    )
    artifacts.verify_saved_schema(paths, bundle, feature_columns)
    report_paths = artifacts.save_reports(config, bundle)

    for label, path in list(paths.items()) + list(report_paths.items()):
        if path.exists():
            say(f"      {label:<16} {path}")

    return PipelineResult(bundle, paths, report_paths)
