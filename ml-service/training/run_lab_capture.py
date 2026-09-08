import argparse
import json
import statistics
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import capture_source, lab_runner, manifest as manifest_module
from app.live import protocol, session
from training import live_report

DEFAULT_MANIFESTS = _ML_SERVICE_ROOT / "training" / "configs" / "live"
DEFAULT_REPORTS = _ML_SERVICE_ROOT / "reports" / "live_evaluation"


class StoppingCondition:
    def __init__(self, min_valid_flows=None):
        self.min_valid_flows = min_valid_flows
        self.valid_flows = 0

    def note(self, record):
        if record.get("validation_status") == protocol.STATUS_VALID:
            self.valid_flows += 1

    def reached(self):
        if self.min_valid_flows is None:
            return False
        return self.valid_flows >= self.min_valid_flows


def latency_summary(records):
    model = [r["model_inference_latency_ms"] for r in records
             if r.get("model_inference_latency_ms") is not None]
    production = [r["production_path_inference_latency_ms"] for r in records
                  if r.get("production_path_inference_latency_ms") is not None]

    def describe(values):
        if not values:
            return None
        ordered = sorted(values)
        return {
            "n": len(ordered),
            "mean_ms": float(statistics.fmean(ordered)),
            "median_ms": float(statistics.median(ordered)),
            "p95_ms": float(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]),
            "min_ms": float(ordered[0]),
            "max_ms": float(ordered[-1]),
        }

    return {
        protocol.LATENCY_MODEL_INFERENCE: describe(model),
        protocol.LATENCY_PRODUCTION_PATH: describe(production),
        protocol.LATENCY_END_TO_END: None,
        "note": protocol.LATENCY_LAYER_NOTE,
    }


def run(manifest, capture_path, models_dir, reports_dir, follow=False,
        duration_seconds=None, poll_interval=2.0, min_valid_flows=None,
        idle_timeout=None, max_rows=None, stop_after_valid_flows=None):
    model, label_encoder, feature_columns, identity = lab_runner.load_frozen_model(
        models_dir)
    validator = lab_runner.build_validator(feature_columns)

    print(f"[lab] model {identity['model_name']} v{identity['model_version']} "
          f"sha_verified={identity['sha_verified']} "
          f"schema={identity['feature_schema']} features={identity['feature_count']}")
    print(f"[lab] run {manifest.run_id} scenario={manifest.scenario_id} "
          f"expected={manifest.expected_binary_label}")

    source = capture_source.CsvFlowSource(capture_path)
    run_session = session.RunSession(manifest, reports_dir, model_identity=identity)
    stopping = StoppingCondition(stop_after_valid_flows)
    run_session.start()
    print(f"[lab] status={run_session.state['status']} "
          f"actual_start={run_session.state['actual_start']}")

    aborted = None
    try:
        if follow:
            stream = source.follow(poll_interval=poll_interval,
                                   duration_seconds=duration_seconds,
                                   max_rows=max_rows,
                                   stop_predicate=stopping.reached,
                                   idle_timeout=idle_timeout)
        else:
            stream = iter(source.read_all())

        for row in stream:
            record, _ = lab_runner.process_row(row, manifest, model, label_encoder,
                                               feature_columns, validator, identity)
            run_session.record(record)
            stopping.note(record)
            if run_session.state["flow_count"] % 100 == 0:
                print(f"[lab] {run_session.state['flow_count']} flows "
                      f"({run_session.state['valid_flow_count']} valid)")
    except KeyboardInterrupt:
        aborted = "interrupted by operator"
    except Exception as error:
        aborted = f"{type(error).__name__}: {error}"

    if aborted:
        run_session.abort(aborted)
        print(f"[lab] ABORTED: {aborted}", file=sys.stderr)
    else:
        run_session.stop()

    state = run_session.finalize()
    print(f"[lab] status={state['status']} flows={state['flow_count']} "
          f"valid={state['valid_flow_count']} invalid={state['invalid_flow_count']} "
          f"unlabelled={state['unlabelled_flow_count']} "
          f"predictions={state['prediction_count']}")

    run_dir = Path(reports_dir) / "runs" / manifest.run_id
    timings = latency_summary(run_session.flows)
    with open(run_dir / "timings.json", "w", encoding="utf-8") as handle:
        json.dump(timings, handle, indent=1)

    if state["status"] != protocol.RUN_COMPLETED:
        print(f"[lab] run nuk eshte COMPLETED; asnje metrike nuk gjenerohet.",
              file=sys.stderr)
        return state, None, timings

    if min_valid_flows is not None and state["valid_flow_count"] < min_valid_flows:
        run_session.invalidate(
            f"valid flow target not met: {state['valid_flow_count']} < {min_valid_flows}")
        run_session.finalize()
        print(f"[lab] INVALID: objektivi i flow-ve te vlefshme nuk u arrit.",
              file=sys.stderr)
        return run_session.state, None, timings

    report = live_report.evaluate_run(run_dir)
    return state, report, timings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kapje reale laboratorike: CICFlowMeter CSV -> modeli i ngrire -> ledger")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS))
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--min-valid-flows", type=int, default=None)
    parser.add_argument("--stop-after-valid-flows", type=int, default=None)
    parser.add_argument("--idle-timeout", type=float, default=None)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        manifest_path = DEFAULT_MANIFESTS / args.manifest
    manifest = manifest_module.load(manifest_path)

    min_valid = (args.min_valid_flows if args.min_valid_flows is not None
                 else manifest.min_valid_flows)
    duration = args.duration if args.duration is not None else None

    state, report, timings = run(
        manifest, args.capture, args.models_dir, args.reports_dir,
        follow=args.follow, duration_seconds=duration,
        poll_interval=args.poll_interval, min_valid_flows=min_valid,
        idle_timeout=args.idle_timeout, max_rows=args.max_rows,
        stop_after_valid_flows=args.stop_after_valid_flows)

    for layer in (protocol.LATENCY_MODEL_INFERENCE, protocol.LATENCY_PRODUCTION_PATH):
        summary = timings.get(layer)
        if summary:
            print(f"[lab] {layer}: median {summary['median_ms']:.3f} ms "
                  f"p95 {summary['p95_ms']:.3f} ms n={summary['n']}")
    print(f"[lab] {protocol.LATENCY_END_TO_END}: not measured, not claimed")

    if report is None:
        return 2

    binary = report["binary"]
    print(f"[lab] evaluable={binary.get('evaluable_flows')} "
          f"benignFPR={binary.get('benign_false_positive_rate')} "
          f"denominator={binary.get('benign_false_positive_rate_denominator')}")

    if args.aggregate:
        payload, path = live_report.write_aggregate(args.reports_dir)
        print(f"[lab] aggregate included={payload['runs_included']} "
              f"excluded={payload['runs_excluded']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
