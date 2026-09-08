import argparse
import sys
from pathlib import Path

import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import lab_runner, manifest as manifest_module, protocol, session
from app.replay.feature_mapping import CICFLOWMETER_TO_CICIDS2017
from training import live_report

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
SMOKE_RUN_ID = "lab-v1-smoke-001"

SMOKE_MANIFEST = {
    "protocol_version": protocol.PROTOCOL_VERSION,
    "experiment_id": protocol.EXPERIMENT_ID,
    "run_id": SMOKE_RUN_ID,
    "scenario_id": "smoke",
    "scenario_description": (
        "Local smoke validation of metadata propagation, validation status, run "
        "lifecycle and report generation. The rows are replayed CICIDS2017 records "
        "renamed into CICFlowMeter column form; no laboratory traffic was captured and "
        "no VM was involved. This run is NOT a live generalization result."),
    "expected_binary_label": "ATTACK",
    "smoke_test": True,
    "exclude_from_thesis_metrics": True,
    "ground_truth": {
        "mode": manifest_module.GROUND_TRUTH_SELECTOR,
        "unmatched_policy": manifest_module.UNMATCHED_BENIGN,
        "attack_selector": {"source_ip": "192.168.50.10",
                            "destination_ip": "192.168.50.20"},
        "rationale": ("synthetic selector exercising the per-flow ground-truth path; "
                      "unmatched rows are declared BENIGN here only so the smoke run "
                      "exercises both metric denominators"),
    },
    "model": {"name": protocol.FROZEN_PRIMARY_MODEL["name"],
              "version": protocol.FROZEN_PRIMARY_MODEL["version"],
              "feature_version": protocol.FROZEN_PRIMARY_MODEL["feature_version"],
              "artifact_file": protocol.FROZEN_PRIMARY_MODEL["artifact_file"]},
    "capture": {"interface": "none", "source": "replayed_rows_renamed_to_cicflowmeter"},
    "topology": {"source_host": "192.168.50.10", "source_role": "synthetic",
                 "target_host": "192.168.50.20", "target_role": "synthetic",
                 "network": "no network was used"},
    "notes": "smoke_test = true, exclude_from_thesis_metrics = true",
}


def cicids_to_cicflowmeter():
    inverted = {}
    for cicflow_name, cicids_name in CICFLOWMETER_TO_CICIDS2017.items():
        inverted.setdefault(cicids_name, cicflow_name)
    return inverted


def build_rows(dataset_path, feature_columns, limit, seed=42):
    frame = pd.read_parquet(dataset_path, columns=feature_columns + ["Label"])
    sample = frame.sample(n=min(limit, len(frame)), random_state=seed)

    inverted = cicids_to_cicflowmeter()
    rows = []
    for position, (_, record) in enumerate(sample.iterrows()):
        row = {}
        for name in feature_columns:
            row[inverted.get(name, name)] = record[name]
        benign = str(record["Label"]).strip() == "BENIGN"
        row["src_ip"] = "192.168.50.99" if benign else "192.168.50.10"
        row["dst_ip"] = "192.168.50.20"
        row["src_port"] = 40000 + position
        row["timestamp"] = f"2026-09-07 12:{position % 60:02d}:00"
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke lokal i rrugës laboratorike (pa VM, pa trafik real)")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--reports-dir", default="reports/live_evaluation")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    manifest = manifest_module.validate(SMOKE_MANIFEST, source="live_smoke.py")
    if not manifest.smoke_test or not manifest.exclude_from_thesis_metrics:
        raise SystemExit("smoke manifest duhet te jete i shenuar si smoke_test")

    model, label_encoder, feature_columns, identity = lab_runner.load_frozen_model(
        args.models_dir)
    validator = lab_runner.build_validator(feature_columns)

    print(f"[smoke] Model: {identity['model_name']} v{identity['model_version']} "
          f"({identity['feature_count']} features, sha ok={identity['sha_verified']})")

    rows = build_rows(args.dataset, feature_columns, args.limit)
    print(f"[smoke] {len(rows)} rreshta te riemertuar ne forme cicflowmeter")

    run = session.RunSession(manifest, args.reports_dir, model_identity=identity)
    run.start()
    for row in rows:
        record, _ = lab_runner.process_row(row, manifest, model, label_encoder,
                                           feature_columns, validator, identity)
        run.record(record)
    run.stop()
    state = run.finalize()

    print(f"[smoke] status={state['status']} flows={state['flow_count']} "
          f"valid={state['valid_flow_count']} invalid={state['invalid_flow_count']} "
          f"predictions={state['prediction_count']}")

    report = live_report.evaluate_run(Path(args.reports_dir) / "runs" / SMOKE_RUN_ID)
    binary = report["binary"]
    print(f"[smoke] evaluable={binary.get('evaluable_flows')} "
          f"detection={binary.get('attack_detection_rate')} "
          f"denominator={binary.get('attack_detection_rate_denominator')} "
          f"benignFPR={binary.get('benign_false_positive_rate')}")
    print(f"[smoke] smoke_test={report['smoke_test']} "
          f"exclude_from_thesis_metrics={report['exclude_from_thesis_metrics']}")

    payload, path = live_report.write_aggregate(args.reports_dir)
    print(f"[smoke] aggregate: included={payload['runs_included']} "
          f"excluded={payload['runs_excluded']}")
    print(f"[smoke] U ruajt: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
