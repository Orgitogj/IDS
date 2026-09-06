import argparse
import json
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import historical, registration
from training.pipeline.reporting import (
    ARTIFACT_MISMATCH,
    ARTIFACT_OK,
    EvaluationReport,
    EvaluationReportError,
)

DEFAULT_REPORTS_DIR = "reports/artifact_evaluation"
DEFAULT_MODELS_DIR = "models"

BANNER_DRY_RUN = """
+---------------------------------------------------------------+
|  DRY RUN - asgje nuk shkruhet ne PostgreSQL.                  |
|  Per te shkruar vertet duhet --commit (dhe konfirmim me -y).  |
+---------------------------------------------------------------+
"""

BANNER_COMMIT = """
+---------------------------------------------------------------+
|  COMMIT - kjo SHKRUAN rreshta te rinj ne experiment_results.  |
+---------------------------------------------------------------+
"""


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


def discover_reports(reports_dir):
    found = []
    for path in sorted(reports_dir.glob("*/metrics.json")):
        try:
            found.append(EvaluationReport.from_path(path))
        except EvaluationReportError as error:
            print(f"  [skip] {path.parent.name}: {error}", file=sys.stderr)
    return found


def fetch_models(client):
    return client._request("GET", "/api/models")


def supersession_note(report):
    note = {
        "result_kind": "recomputed_from_artifact",
        "registration_source": "training.reregister_experiments",
        "overwrites_previous_rows": False,
    }

    stored = historical.stored_for(report.name)
    if not stored:
        note["historical_stored_values"] = None
        note["historical_note"] = historical.UNRECOVERABLE_OFFLINE
        return note

    note["historical_stored_values"] = {
        field: historical.stored_value(report.name, field)
        for field in ("accuracy", "precisionScore", "recall", "f1Score",
                      "avgLatencyMs", "sampleSize")
    }
    note["historical_hardcoded_fields"] = historical.hardcoded_fields(report.name)
    note["historical_source"] = (
        f"{historical.SOURCE_NOTEBOOK} cell {stored['notebook_cell']}")
    return note


def print_comparison(report):
    stored = historical.stored_for(report.name)
    if not stored:
        return

    hardcoded = historical.hardcoded_fields(report.name)
    print(f"    vlerat historike (nga cell {stored['notebook_cell']} i notebook-ut):")
    print(f"      {'field':<16}{'stored':>14}{'recomputed':>14}{'difference':>14}  origin")

    pairs = [
        ("accuracy", report.overall["accuracy"]),
        ("precisionScore", report.overall["macro_precision"]),
        ("recall", report.overall["macro_recall"]),
        ("f1Score", report.overall["macro_f1"]),
        ("avgLatencyMs", report.batch_latency_ms),
        ("sampleSize", float(report.sample_size)),
    ]

    for field, recomputed in pairs:
        stored_value = historical.stored_value(report.name, field)
        if stored_value is None or recomputed is None:
            continue
        entry = stored.get(field)
        origin = entry.get("origin") if isinstance(entry, dict) else historical.ORIGIN_UNKNOWN
        flag = "  <- HARDCODED" if field in hardcoded else ""
        if field == "avgLatencyMs":
            flag += "  (hardware-dependent, not a reproducibility check)"
        print(f"      {field:<16}{float(stored_value):>14.6f}{float(recomputed):>14.6f}"
              f"{float(recomputed) - float(stored_value):>+14.6f}  {origin}{flag}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regjistron rezultatet e eksperimenteve VETEM nga raporte evaluation "
                    "te validuara. Dry-run eshte default.")
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--report", default=None,
                        help="Regjistro nje raport te vetem ne vend te gjithe direktorise")
    parser.add_argument("--only", default=None,
                        help="Filtro sipas emrit te eksperimentit")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Default. Nuk prek as rrjetin as databazen.")
    parser.add_argument("--commit", action="store_true",
                        help="Shkruaj vertet ne PostgreSQL nepermjet backend-it")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Kalo konfirmimin interaktiv (kerkohet me --commit)")
    parser.add_argument("--allow-hash-mismatch", action="store_true",
                        help="Vazhdo edhe nese SHA256 i artefaktit ndryshon nga raporti")
    args = parser.parse_args()

    if args.commit and not args.yes:
        print("GABIM: --commit shkruan ne PostgreSQL dhe kerkon edhe --yes. "
              "Xhiro fillimisht pa asnje flag per dry-run.", file=sys.stderr)
        return 1

    dry_run = not args.commit
    print(BANNER_DRY_RUN if dry_run else BANNER_COMMIT)

    models_dir = resolve(args.models_dir)

    if args.report:
        try:
            reports = [EvaluationReport.from_path(resolve(args.report))]
        except EvaluationReportError as error:
            print(f"GABIM: {error}", file=sys.stderr)
            return 1
    else:
        reports_dir = resolve(args.reports_dir)
        if not reports_dir.exists():
            print(f"GABIM: {reports_dir} s'ekziston. Xhiro fillimisht "
                  "'python -m training.evaluate_artifacts'.", file=sys.stderr)
            return 1
        reports = discover_reports(reports_dir)

    if args.only:
        reports = [report for report in reports if args.only in report.name]

    if not reports:
        print("Asnje raport i vlefshem per t'u regjistruar.", file=sys.stderr)
        return 1

    registry = {}
    client = None
    if not dry_run:
        from app.services import spring_client

        client = spring_client
        try:
            registry = {entry["name"]: entry for entry in fetch_models(client)}
        except Exception as error:
            print(f"GABIM: regjistri i modeleve s'u arrit ({error}).", file=sys.stderr)
            return 1

    planned = []
    blocked = []

    for report in reports:
        print(f"\n=== {report.name} ===")
        print(f"  artefakt      : {report.artifact_file}")
        print(f"  sha256        : {report.artifact_sha256[:16]}...")
        print(f"  dataset       : {report.dataset_name}")
        print(f"  feature set   : {report.feature_version}")
        print(f"  test rows     : {report.sample_size:,}")
        if report.subsampled:
            print("  KUJDES        : raporti u prodhua mbi nen-mostre; nuk eshte "
                  "i krahasueshem me rezultatet historike.")

        status, actual = report.verify_artifact(models_dir)
        print(f"  artifact hash : {status}")
        if status == ARTIFACT_MISMATCH:
            print(f"    raporti : {report.artifact_sha256}")
            print(f"    ne disk : {actual}")
        if status != ARTIFACT_OK and not args.allow_hash_mismatch:
            blocked.append((report.name, f"artifact {status}"))
            print("  -> BLLOKUAR (kalo --allow-hash-mismatch nese e di cfare po ben)")
            continue

        overall = report.overall
        print(f"  accuracy {overall['accuracy']:.6f} | macro P "
              f"{overall['macro_precision']:.6f} | macro R "
              f"{overall['macro_recall']:.6f} | macro F1 {overall['macro_f1']:.6f}")
        latency = report.batch_latency_ms
        if latency is not None:
            print(f"  batch latency {latency:.6f} ms/flow (metodologjia historike)")
        single = report.single_flow_latency
        if single:
            print(f"  single-flow   mean {single['mean_ms']:.4f} ms | median "
                  f"{single['median_ms']:.4f} ms | p95 {single['p95_ms']:.4f} ms")

        print_comparison(report)

        model_id, entry = registration.resolve_model_id(
            list(registry.values()), report)
        if dry_run:
            model_id = model_id or "<do te zgjidhet nga regjistri ne --commit>"
        elif model_id is None:
            blocked.append((report.name, "model not in registry"))
            print(f"  -> BLLOKUAR: '{report.name}' s'u gjet ne regjistrin e modeleve")
            continue

        try:
            outcome = registration.register(
                report, model_id, client, models_dir, dry_run=dry_run,
                allow_mismatch=args.allow_hash_mismatch,
                extra_provenance=supersession_note(report))
        except registration.RegistrationError as error:
            blocked.append((report.name, str(error)))
            print(f"  -> BLLOKUAR: {error}")
            continue

        planned.append((report, outcome))
        payload = outcome["payload"]
        print(f"  payload       : accuracy={payload['accuracy']:.6f} "
              f"f1={payload['f1Score']:.6f} n={payload['sampleSize']:,}")
        print(f"  provenance    : {len(payload['notes'])} chars")
        if outcome["written"]:
            print(f"  -> SHKRUAR: id={outcome['response'].get('id')}")
        else:
            print("  -> do te shkruhej nje rresht i ri ne experiment_results")

    print(f"\n--- Permbledhje ---")
    print(f"Raporte te lexuara : {len(reports)}")
    print(f"Gati per regjistrim: {len(planned)}")
    print(f"Te bllokuara       : {len(blocked)}")
    for name, reason in blocked:
        print(f"  - {name}: {reason}")

    if dry_run:
        print("\nAsgje nuk u shkrua. Perdor --commit -y kur te jesh gati.")
        print(f"Shenim: {historical.UNRECOVERABLE_OFFLINE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
