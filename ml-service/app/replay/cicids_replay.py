import argparse
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import requests

from app.core.config import settings
from app.ml.inference import load_artifacts, predict
from app.services.spring_client import ingest_flow

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_DATASET = "cicids2017_cleaned.parquet"
DATASET_SOURCE = "CICIDS2017_REPLAY"

PROTOCOL_NAMES = {0: "HOPOPT", 1: "ICMP", 6: "TCP", 17: "UDP"}

TIMESTAMP_FORMATS = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]

MAX_CONSECUTIVE_ERRORS = 5


def _clean_label(label: str) -> str:
    return str(label).replace("\x96", "-").strip()


def _protocol_name(value) -> str:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return "UNKNOWN"
    return PROTOCOL_NAMES.get(number, str(number))


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value):
    if isinstance(value, datetime):
        return value
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def _iso_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _select_indices(dataset_path: Path, limit: int, attack_ratio: float, seed: int):
    labels = pq.read_table(dataset_path, columns=["Label"]).column("Label").to_pylist()

    benign, attack = [], []
    for index, label in enumerate(labels):
        (benign if _clean_label(label) == "BENIGN" else attack).append(index)

    wanted_attack = min(int(limit * attack_ratio), len(attack))
    wanted_benign = min(limit - wanted_attack, len(benign))

    rng = random.Random(seed)
    chosen = rng.sample(attack, wanted_attack) + rng.sample(benign, wanted_benign)
    rng.shuffle(chosen)

    print(f"Zgjodha {len(chosen)} flows: {wanted_attack} sulme, {wanted_benign} benign "
          f"(nga {len(labels):,} rreshta gjithsej).")
    return chosen


def _collect_rows(dataset_path: Path, indices):
    wanted = set(indices)
    parquet_file = pq.ParquetFile(dataset_path)

    collected = {}
    offset = 0
    for batch in parquet_file.iter_batches(batch_size=50_000):
        hits = [i - offset for i in range(offset, offset + batch.num_rows) if i in wanted]
        if hits:
            frame = batch.to_pandas().iloc[hits]
            for local_position, local_index in enumerate(hits):
                collected[local_index + offset] = frame.iloc[local_position]
        offset += batch.num_rows
        if len(collected) >= len(wanted):
            break

    return [collected[i] for i in indices if i in collected]


def _build_payload(row, feature_columns, preserve_timestamps: bool):
    feature_vector = {column: float(row[column]) for column in feature_columns}

    prediction = predict(feature_vector, include_shap=False)
    predicted = _clean_label(prediction["predicted_label"])

    is_attack = predicted != "BENIGN"
    flow_time = _parse_timestamp(row["Timestamp"]) if preserve_timestamps else None

    return {
        "source_ip": str(row["Source IP"]),
        "destination_ip": str(row["Destination IP"]),
        "source_port": _to_int(row["Source Port"]),
        "destination_port": _to_int(row["Destination Port"]),
        "protocol": _protocol_name(row["Protocol"]),
        "feature_vector": feature_vector,
        "predicted_label": "ATTACK" if is_attack else "BENIGN",
        "prediction_confidence": prediction["confidence"],
        "attack_type": predicted if is_attack else None,
        "flow_timestamp_iso": _iso_utc(flow_time or datetime.now(timezone.utc)),
        "dataset_source": DATASET_SOURCE,
    }


def replay(args) -> int:
    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        datasets_dir = settings.datasets_dir.lstrip("./")
        dataset_path = _ML_SERVICE_ROOT / datasets_dir / args.dataset
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    load_artifacts()
    from app.ml.inference import _feature_columns

    indices = _select_indices(dataset_path, args.limit, args.attack_ratio, args.seed)
    print("Duke lexuar rreshtat e zgjedhur nga parquet...")
    rows = _collect_rows(dataset_path, indices)
    print(f"{len(rows)} rreshta gati.\n")

    if args.dry_run:
        print("DRY RUN - asgje s'dergohet te Spring Boot.\n")
    else:
        print(f"Duke derguar te {settings.spring_boot_base_url}/api/alarms/ingest "
              f"me {args.rate} flows/sek...\n")

    interval = 1.0 / args.rate if args.rate > 0 else 0.0
    next_send = time.perf_counter()
    started = time.perf_counter()

    sent = attacks = errors = 0
    consecutive_errors = 0

    try:
        for position, row in enumerate(rows, start=1):
            payload = _build_payload(row, _feature_columns, args.preserve_timestamps)
            if payload["predicted_label"] == "ATTACK":
                attacks += 1

            if args.dry_run:
                sent += 1
            else:
                try:
                    ingest_flow(**payload)
                    sent += 1
                    consecutive_errors = 0
                except requests.exceptions.RequestException as error:
                    errors += 1
                    consecutive_errors += 1
                    print(f"  gabim ne flow {position}: {error}", file=sys.stderr)
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        print(f"\n{MAX_CONSECUTIVE_ERRORS} gabime rresht - "
                              f"a eshte Spring Boot i ndezur? Po ndaloj.", file=sys.stderr)
                        break

            if position % 50 == 0:
                print(f"  {position}/{len(rows)} flows - {attacks} sulme te parashikuara")

            if interval:
                next_send += interval
                pause = next_send - time.perf_counter()
                if pause > 0:
                    time.sleep(pause)
    except KeyboardInterrupt:
        print("\nNderprere nga perdoruesi.")

    elapsed = time.perf_counter() - started
    print("\n--- Permbledhje ---")
    print(f"Derguar:          {sent}")
    print(f"Sulme (alarme):   {attacks}")
    print(f"Gabime:           {errors}")
    if elapsed > 0:
        print(f"Kohe:             {elapsed:.1f}s ({sent / elapsed:.1f} flows/sek)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay i CICIDS2017 drejt pipeline-it IDS.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET,
                        help=f"Emri ose rruga e dataset-it (default: {DEFAULT_DATASET})")
    parser.add_argument("--limit", type=int, default=500,
                        help="Sa flows te dergohen (default: 500)")
    parser.add_argument("--rate", type=float, default=10.0,
                        help="Flows per sekonde; 0 = sa me shpejt (default: 10)")
    parser.add_argument("--attack-ratio", type=float, default=0.3,
                        help="Pjesa e flows qe jane sulme reale (default: 0.3)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed per zgjedhjen e rreshtave (default: 42)")
    parser.add_argument("--preserve-timestamps", action="store_true",
                        help="Perdor timestamp-et origjinale 2017 ne vend te kohes aktuale")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parashiko pa derguar asgje te Spring Boot")
    return replay(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
