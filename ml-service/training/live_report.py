import argparse
import json
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import manifest as manifest_module
from app.live import protocol, session
from training.pipeline import live

REPORTS = _ML_SERVICE_ROOT / "reports" / "live_evaluation"
MANIFESTS = _ML_SERVICE_ROOT / "training" / "configs" / "live"


def protocol_document():
    return {
        "schema_version": 1,
        "experiment_type": "live_lab",
        "protocol_version": protocol.PROTOCOL_VERSION,
        "experiment_id": protocol.EXPERIMENT_ID,
        "objective": (
            "Evaluate whether the frozen CICIDS2017-trained supervised classifier retains "
            "useful attack-detection ability on traffic generated outside the benchmark "
            "dataset, in a controlled isolated laboratory testbed."),
        "not_a_claim_about": [
            "production validation",
            "arbitrary zero-day detection",
            "unseen attack families - that question is answered by lofo-v1",
        ],
        "separate_from": {
            "random-v2": "reports/artifact_evaluation",
            "temporal-v1": "reports/temporal_evaluation",
            "lofo-v1": "reports/lofo_evaluation",
        },
        "frozen_primary_model": protocol.FROZEN_PRIMARY_MODEL,
        "validation_statuses": protocol.VALIDATION_STATUSES,
        "validation_status_note": protocol.VALIDATION_STATUS_NOTE,
        "run_statuses": protocol.RUN_STATUSES,
        "evaluable_run_statuses": protocol.EVALUABLE_RUN_STATUSES,
        "expected_binary_labels": protocol.EXPECTED_BINARY_LABELS,
        "ground_truth_modes": manifest_module.GROUND_TRUTH_MODES,
        "unmatched_policies": manifest_module.UNMATCHED_POLICIES,
        "extra_feature_policy": protocol.EXTRA_FEATURE_POLICY,
        "extra_feature_policy_note": protocol.EXTRA_FEATURE_POLICY_NOTE,
        "capture_time_sources": protocol.CAPTURE_TIME_SOURCES,
        "capture_time_note": protocol.CAPTURE_TIME_NOTE,
        "latency_layers": [protocol.LATENCY_MODEL_INFERENCE,
                           protocol.LATENCY_PRODUCTION_PATH,
                           protocol.LATENCY_END_TO_END],
        "latency_layer_note": protocol.LATENCY_LAYER_NOTE,
        "benign_fpr_definition": protocol.BENIGN_FPR_DEFINITION,
        "detection_definition": protocol.DETECTION_DEFINITION,
        "attribution_definition": protocol.ATTRIBUTION_DEFINITION,
        "minimum_support_for_rate": live.MIN_SUPPORT_FOR_RATE,
    }


def write_protocol(reports_dir=None):
    directory = Path(reports_dir or REPORTS)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "protocol.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(protocol_document(), handle, indent=1)
    return path


def evaluate_run(run_dir, manifests_dir=None):
    run_dir = Path(run_dir)
    state = session.load_state(run_dir)
    flows = session.load_flows(run_dir)

    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        run_manifest = manifest_module.validate(payload, source=str(manifest_path))
    else:
        run_manifest = manifest_module.load(
            Path(manifests_dir or MANIFESTS) / f"{state['run_id']}.yaml")

    report = live.run_report(run_manifest, flows, state)
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    return report


def collect_run_reports(reports_dir=None):
    root = Path(reports_dir or REPORTS) / "runs"
    reports = []
    if not root.exists():
        return reports
    for directory in sorted(root.iterdir()):
        path = directory / "metrics.json"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as handle:
            reports.append(json.load(handle))
    return reports


def write_aggregate(reports_dir=None):
    directory = Path(reports_dir or REPORTS)
    directory.mkdir(parents=True, exist_ok=True)
    payload = live.aggregate(collect_run_reports(directory))
    path = directory / "aggregate.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
    return payload, path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Raportim per eksperimentin laboratorik live (live-lab-v1)")
    parser.add_argument("--reports-dir", default=str(REPORTS))
    parser.add_argument("--write-protocol", action="store_true")
    parser.add_argument("--evaluate-run", default=None)
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--list-interrupted", action="store_true")
    args = parser.parse_args()

    if args.write_protocol:
        print(f"U shkrua: {write_protocol(args.reports_dir)}")

    if args.list_interrupted:
        stale = session.interrupted_runs(args.reports_dir)
        if not stale:
            print("Asnje run i nderprere.")
        for entry in stale:
            print(f"  I NDERPRERE: {entry['run_id']} ({entry['status']}) {entry['path']}")

    if args.evaluate_run:
        report = evaluate_run(Path(args.reports_dir) / "runs" / args.evaluate_run)
        print(json.dumps(report["binary"], indent=1))

    if args.aggregate:
        payload, path = write_aggregate(args.reports_dir)
        print(f"U ruajt: {path}")
        print(f"  runs te perfshire: {payload['n_runs']} {payload['runs_included']}")
        print(f"  runs te perjashtuar: {payload['runs_excluded']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
