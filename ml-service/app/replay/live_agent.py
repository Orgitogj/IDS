import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import requests

try:
    from app.replay.feature_mapping import CICFLOWMETER_TO_CICIDS2017, META_COLUMNS
    from app.ml.feature_validation import (STRICT_POLICY, FeatureValidator,
                                           load_reference, verify_feature_version)
    from app.ml.anomaly import load_anomaly_detector
    from app.ml.detection_engine import decide, to_flow_label
    from app.services.token_provider import TokenProvider
except ImportError:
    from feature_mapping import CICFLOWMETER_TO_CICIDS2017, META_COLUMNS
    from feature_validation import (STRICT_POLICY, FeatureValidator, load_reference,
                                    verify_feature_version)
    from anomaly import load_anomaly_detector
    from detection_engine import decide, to_flow_label
    from token_provider import TokenProvider


def load_model_artifacts(models_dir: Path, model_filename: str):

    model = joblib.load(models_dir / model_filename)
    label_encoder = joblib.load(models_dir / "label_encoder_cicids2017.joblib")

    names = getattr(model, "feature_names_in_", None)
    if names is not None:
        return model, label_encoder, [str(c) for c in names]

    expected = getattr(model, "n_features_in_", None)
    sidecar = models_dir / f"{Path(model_filename).stem}_feature_columns.json"

    if sidecar.exists():
        with open(sidecar, encoding="utf-8") as f:
            feature_columns = [str(c) for c in json.load(f)]
        print(f"[live_agent] Modeli s'ka feature_names_in_; schema u lexua nga "
              f"{sidecar.name} ({len(feature_columns)} features).", file=sys.stderr)
    else:
        with open(models_dir / "feature_columns.json") as f:
            feature_columns = [str(c) for c in json.load(f)]
        print("[live_agent] KUJDES: modeli s'ka feature_names_in_ dhe s'ka sidecar; "
              "po perdoret feature_columns.json i pergjithshem.", file=sys.stderr)

    if expected is not None and len(feature_columns) != expected:
        raise RuntimeError(
            f"Modeli pret {expected} features por schema e gjetur ka "
            f"{len(feature_columns)}. Kopjo "
            f"'{Path(model_filename).stem}_feature_columns.json' krahas artefaktit.")

    return model, label_encoder, feature_columns


def map_row_to_feature_vector(row: dict) -> dict:

    renamed = {}
    for k, v in row.items():
        if k in META_COLUMNS:
            continue
        cicids_name = CICFLOWMETER_TO_CICIDS2017.get(k)
        if cicids_name:
            renamed[cicids_name] = v

    return renamed


def predict_flow(model, label_encoder, vector: list):

    x = np.array([vector])
    pred_idx = model.predict(x)[0]
    pred_proba = model.predict_proba(x)[0]
    confidence = float(pred_proba[pred_idx])
    label = label_encoder.inverse_transform([pred_idx])[0]
    return {"predicted_label": label, "confidence": confidence}


def report_validation(validation, row_number: int):

    if validation.derived_features:
        names = ", ".join(entry["feature"] for entry in validation.derived_features)
        print(f"[live_agent] flow {row_number}: {len(validation.derived_features)} features "
              f"u rindertuan nga kolona te tjera: {names}", file=sys.stderr)

    if validation.zero_filled_features:
        print(f"[live_agent] flow {row_number}: {len(validation.zero_filled_features)} features "
              f"konstante-zero u mbushen me 0 (ekzakte ne trajnim)", file=sys.stderr)

    if validation.out_of_range_features:
        print(f"[live_agent] flow {row_number}: {len(validation.out_of_range_features)} features "
              f"jashte intervalit p01-p99 te trajnimit", file=sys.stderr)

    if not validation.valid:
        print(f"[live_agent] flow {row_number} U REFUZUA ({validation.summary()})", file=sys.stderr)
        for warning in validation.warnings:
            print(f"[live_agent]   - {warning}", file=sys.stderr)


def fetch_active_model(backend_url: str, tokens: TokenProvider):

    try:
        resp = authorized_request(tokens, "GET", f"{backend_url}/api/models/active", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[live_agent] KUJDES: regjistri i modeleve s'u arrit ({e}). "
              f"Parashikimet do te dergohen pa identitet modeli.", file=sys.stderr)
        return None


def resolve_model_identity(active, model_file: str):

    if active is None:
        return {}

    registry_file = Path(str(active.get("artifactPath", ""))).name
    if registry_file != model_file:
        print(f"[live_agent] KUJDES: artefakti lokal '{model_file}' NUK eshte modeli aktiv "
              f"ne regjistrin e modeleve ('{registry_file}'). Alarmet do te shenohen me "
              f"modelin qe u perdor vertet, jo me ate aktiv.", file=sys.stderr)
        return {}

    return {
        "modelId": active.get("id"),
        "modelName": active.get("name"),
        "modelVersion": active.get("version"),
        "featureVersion": active.get("featureVersion"),
    }


def authorized_request(tokens: TokenProvider, method: str, url: str,
                       payload: dict = None, timeout: int = 10):

    for attempt in range(2):
        resp = requests.request(method, url, json=payload,
                                headers=tokens.authorization_header(force_refresh=attempt > 0),
                                timeout=timeout)
        if resp.status_code in (401, 403) and attempt == 0:
            continue
        return resp

    return resp


def ingest_flow(backend_url: str, tokens: TokenProvider, row: dict, feature_vector: dict,
                detection: dict, identity: dict = None, feature_version: str = None):

    label = detection["prediction"]
    payload = {
        "sourceIp": row.get("src_ip", "0.0.0.0"),
        "destinationIp": row.get("dst_ip", "0.0.0.0"),
        "sourcePort": int(float(row.get("src_port", 0) or 0)),
        "destinationPort": int(float(row.get("dst_port", 0) or 0)),
        "protocol": "TCP" if row.get("protocol") == "6" else "UDP" if row.get("protocol") == "17" else "OTHER",
        "featureVector": feature_vector,
        "predictedLabel": to_flow_label(detection["detection_class"]),
        "predictionConfidence": detection["confidence"],
        "attackType": label if detection["detection_class"] == "KNOWN_ATTACK" else None,
        "detectionMethod": detection["detection_method"],
        "anomalyScore": detection["anomaly_score"],
        "flowTimestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(identity or {})
    if not payload.get("featureVersion"):
        payload["featureVersion"] = feature_version
    try:
        resp = authorized_request(tokens, "POST", f"{backend_url}/api/alarms/ingest",
                                  payload=payload, timeout=5)
        resp.raise_for_status()
        confidence_text = ("conf=%.4f" % detection["confidence"]
                           if detection["confidence"] is not None
                           else "anomaly=%.4f" % (detection["anomaly_score"] or 0.0))
        print(f"[live_agent] Ingested: {label} ({confidence_text}) "
              f"{payload['sourceIp']}:{payload['sourcePort']} -> "
              f"{payload['destinationIp']}:{payload['destinationPort']}")
    except requests.RequestException as e:
        print(f"[live_agent] GABIM duke derguar te backend: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Live traffic agent per RQ2 (cicflowmeter -> model -> backend)")
    parser.add_argument("--interface", default="eth0", help="Interface per kapje live (default: eth0)")
    parser.add_argument("--backend", default="http://192.168.100.3:8080", help="Base URL i backend-it Spring Boot")
    parser.add_argument("--models-dir", default=".", help="Folder me .joblib dhe feature_columns.json")
    parser.add_argument("--model-file", default="xgb_smote_top50features_v1.joblib",
                         help="Emri i file-it .joblib per t'u ngarkuar (default: top-50 features, "
                              "me risk me te ulet drift-i sesa modeli me 78 features)")
    parser.add_argument("--cicflowmeter-path", default="/usr/local/bin/cicflowmeter",
                         help="Path drejt executable-it cicflowmeter")
    parser.add_argument("--csv-out", default="live_flows.csv", help="File i perkohshem per output te cicflowmeter")
    parser.add_argument("--poll-interval", type=float, default=5.0,
                         help="Sa shpesh (sekonda) te kontrollohet CSV-ja per rreshta te rinj")
    parser.add_argument("--reference", default=None,
                         help="Path drejt training_feature_reference.json per kontrollin e intervaleve")
    parser.add_argument("--no-anomaly-detection", action="store_true",
                         help="Cakivizo detektorin e anomalive dhe perdor vetem modelin e mbikeqyrur")
    parser.add_argument("--anomaly-threshold-rate", default="0.010",
                         help="Shkalla e synuar e flamurimit te BENIGN (default: 0.010)")
    parser.add_argument("--feature-version", default=None,
                         help="Emri i feature set-it (p.sh. cicids2017-top50-v1); zbulohet vete "
                              "nese --reference eshte i pranishem")
    parser.add_argument("--username", default="ml-service", help="Username per login te backend")
    parser.add_argument("--password", default="ml-service-secret", help="Password per login te backend")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    print(f"[live_agent] Duke ngarkuar modelin '{args.model_file}' nga {models_dir} ...")
    model, label_encoder, feature_columns = load_model_artifacts(models_dir, args.model_file)
    print(f"[live_agent] Modeli u ngarkua. {len(feature_columns)} features, "
          f"{len(label_encoder.classes_)} klasa: {list(label_encoder.classes_)}")

    reference = load_reference(args.reference)
    if reference is None:
        print("[live_agent] KUJDES: referenca e trajnimit s'u gjet - "
              "kontrolli i intervaleve eshte i cakivizuar (perdor --reference).", file=sys.stderr)
    mismatch = verify_feature_version(feature_columns, args.feature_version, reference)
    if mismatch is not None:
        print(f"[live_agent] NDALESE: {mismatch['message']}", file=sys.stderr)
        print(f"[live_agent] Feature set-i qe i pergjigjet vertet artefaktit: "
              f"{mismatch['resolved_feature_version']}", file=sys.stderr)
        return 1

    validator = FeatureValidator(feature_columns, reference=reference,
                                 feature_version=args.feature_version, policy=STRICT_POLICY)
    print(f"[live_agent] Validimi aktiv: feature_version={validator.feature_version}, "
          f"politika={validator.policy.name} (flows te pavlefshem refuzohen)")
    anomaly_detector = None
    if not args.no_anomaly_detection:
        anomaly_detector = load_anomaly_detector(
            models_dir, threshold_rate=args.anomaly_threshold_rate)
        if anomaly_detector is None:
            print("[live_agent] KUJDES: artefakti i detektorit te anomalive mungon; "
                  "po vazhdoj vetem me modelin e mbikeqyrur.", file=sys.stderr)
        else:
            print(f"[live_agent] Detektor anomalish aktiv: "
                  f"{anomaly_detector.artifact_file} "
                  f"(prag={anomaly_detector.threshold:.6f})")

    if validator.feature_version.startswith("unregistered-"):
        print("[live_agent] KUJDES: feature set-i s'u njoh - parashikimet nuk do te jene "
              "te gjurmueshme. Kalo --reference ose --feature-version.", file=sys.stderr)

    print(f"[live_agent] Duke bere login te {args.backend} si '{args.username}' ...")
    tokens = TokenProvider(args.backend, args.username, args.password)
    tokens.token()
    print("[live_agent] Login i suksesshem, token-i rifreskohet vete para skadimit.")

    identity = resolve_model_identity(fetch_active_model(args.backend, tokens), args.model_file)
    if identity:
        print(f"[live_agent] Modeli u konfirmua kunder regjistrit: {identity['modelName']} "
              f"v{identity['modelVersion']}")

    csv_path = Path(args.csv_out)
    if csv_path.exists():
        csv_path.unlink()

    print(f"[live_agent] Duke nisur cicflowmeter ne {args.interface} -> {csv_path} ...")
    proc = subprocess.Popen(
        ["sudo", args.cicflowmeter_path, "-i", args.interface, "-c", str(csv_path)],
    )

    seen_rows = 0
    processed = 0
    rejected = 0
    suspicious = 0
    print(f"[live_agent] Duke monitoruar {csv_path} per flow te rinj (Ctrl+C per te ndaluar) ...")
    try:
        while True:
            time.sleep(args.poll_interval)
            if not csv_path.exists():
                continue

            with open(csv_path, newline="") as f:
                reader = list(csv.DictReader(f))

            new_rows = reader[seen_rows:]
            for offset, row in enumerate(new_rows):
                processed += 1
                row_number = seen_rows + offset + 1

                validation = validator.validate(map_row_to_feature_vector(row))
                report_validation(validation, row_number)

                if not validation.valid:
                    rejected += 1
                    continue

                feature_vector = dict(zip(feature_columns, validation.vector))
                supervised = predict_flow(model, label_encoder, validation.vector)
                anomaly = (anomaly_detector.score(map_row_to_feature_vector(row))
                           if anomaly_detector else None)
                detection = decide(supervised, anomaly)
                if detection["detection_class"] == "SUSPICIOUS":
                    suspicious += 1
                ingest_flow(args.backend, tokens, row, feature_vector, detection,
                            identity=identity, feature_version=validator.feature_version)
            seen_rows = len(reader)

    except KeyboardInterrupt:
        print("\n[live_agent] Duke ndaluar...")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        rate = (rejected / processed * 100) if processed else 0.0
        print(f"[live_agent] Gjithsej: {processed} flows, {rejected} te refuzuar "
              f"({rate:.1f}%), {suspicious} te dyshimta.")


if __name__ == "__main__":
    sys.exit(main() or 0)
