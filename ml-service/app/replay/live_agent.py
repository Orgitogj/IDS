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

CICFLOWMETER_TO_CICIDS2017 = {
    "dst_port": "Destination Port",
    "protocol": "Protocol",
    "flow_duration": "Flow Duration",
    "tot_fwd_pkts": "Total Fwd Packets",
    "tot_bwd_pkts": "Total Backward Packets",
    "totlen_fwd_pkts": "Total Length of Fwd Packets",
    "totlen_bwd_pkts": "Total Length of Bwd Packets",
    "fwd_pkt_len_max": "Fwd Packet Length Max",
    "fwd_pkt_len_min": "Fwd Packet Length Min",
    "fwd_pkt_len_mean": "Fwd Packet Length Mean",
    "fwd_pkt_len_std": "Fwd Packet Length Std",
    "bwd_pkt_len_max": "Bwd Packet Length Max",
    "bwd_pkt_len_min": "Bwd Packet Length Min",
    "bwd_pkt_len_mean": "Bwd Packet Length Mean",
    "bwd_pkt_len_std": "Bwd Packet Length Std",
    "flow_byts_s": "Flow Bytes/s",
    "flow_pkts_s": "Flow Packets/s",
    "flow_iat_mean": "Flow IAT Mean",
    "flow_iat_std": "Flow IAT Std",
    "flow_iat_max": "Flow IAT Max",
    "flow_iat_min": "Flow IAT Min",
    "fwd_iat_tot": "Fwd IAT Total",
    "fwd_iat_mean": "Fwd IAT Mean",
    "fwd_iat_std": "Fwd IAT Std",
    "fwd_iat_max": "Fwd IAT Max",
    "fwd_iat_min": "Fwd IAT Min",
    "bwd_iat_tot": "Bwd IAT Total",
    "bwd_iat_mean": "Bwd IAT Mean",
    "bwd_iat_std": "Bwd IAT Std",
    "bwd_iat_max": "Bwd IAT Max",
    "bwd_iat_min": "Bwd IAT Min",
    "fwd_psh_flags": "Fwd PSH Flags",
    "bwd_psh_flags": "Bwd PSH Flags",
    "fwd_urg_flags": "Fwd URG Flags",
    "bwd_urg_flags": "Bwd URG Flags",
    "fwd_header_len": "Fwd Header Length",
    "bwd_header_len": "Bwd Header Length",
    "fwd_pkts_s": "Fwd Packets/s",
    "bwd_pkts_s": "Bwd Packets/s",
    "pkt_len_min": "Min Packet Length",
    "pkt_len_max": "Max Packet Length",
    "pkt_len_mean": "Packet Length Mean",
    "pkt_len_std": "Packet Length Std",
    "pkt_len_var": "Packet Length Variance",
    "fin_flag_cnt": "FIN Flag Count",
    "syn_flag_cnt": "SYN Flag Count",
    "rst_flag_cnt": "RST Flag Count",
    "psh_flag_cnt": "PSH Flag Count",
    "ack_flag_cnt": "ACK Flag Count",
    "urg_flag_cnt": "URG Flag Count",
    "cwr_flag_count": "CWE Flag Count",
    "ece_flag_cnt": "ECE Flag Count",
    "down_up_ratio": "Down/Up Ratio",
    "pkt_size_avg": "Average Packet Size",
    "fwd_seg_size_avg": "Avg Fwd Segment Size",
    "bwd_seg_size_avg": "Avg Bwd Segment Size",
    "fwd_byts_b_avg": "Fwd Avg Bytes/Bulk",
    "fwd_pkts_b_avg": "Fwd Avg Packets/Bulk",
    "fwd_blk_rate_avg": "Fwd Avg Bulk Rate",
    "bwd_byts_b_avg": "Bwd Avg Bytes/Bulk",
    "bwd_pkts_b_avg": "Bwd Avg Packets/Bulk",
    "bwd_blk_rate_avg": "Bwd Avg Bulk Rate",
    "subflow_fwd_pkts": "Subflow Fwd Packets",
    "subflow_fwd_byts": "Subflow Fwd Bytes",
    "subflow_bwd_pkts": "Subflow Bwd Packets",
    "subflow_bwd_byts": "Subflow Bwd Bytes",
    "init_fwd_win_byts": "Init_Win_bytes_forward",
    "init_bwd_win_byts": "Init_Win_bytes_backward",
    "fwd_act_data_pkts": "act_data_pkt_fwd",
    "fwd_seg_size_min": "min_seg_size_forward",
    "active_mean": "Active Mean",
    "active_std": "Active Std",
    "active_max": "Active Max",
    "active_min": "Active Min",
    "idle_mean": "Idle Mean",
    "idle_std": "Idle Std",
    "idle_max": "Idle Max",
    "idle_min": "Idle Min",
}

META_COLUMNS = {"src_ip", "dst_ip", "src_port", "timestamp"}


def load_model_artifacts(models_dir: Path, model_filename: str):

    model = joblib.load(models_dir / model_filename)
    label_encoder = joblib.load(models_dir / "label_encoder_cicids2017.joblib")

    if hasattr(model, "feature_names_in_"):
        feature_columns = [str(c) for c in model.feature_names_in_]
    else:

        print("[live_agent] KUJDES: modeli s'ka feature_names_in_, "
              "duke perdorur feature_columns.json te plote (78) si fallback",
              file=sys.stderr)
        with open(models_dir / "feature_columns.json") as f:
            feature_columns = json.load(f)

    return model, label_encoder, feature_columns


def map_row_to_feature_vector(row: dict, feature_columns: list) -> dict:

    mapped = {}
    missing = []
    renamed = {}
    for k, v in row.items():
        if k in META_COLUMNS:
            continue
        cicids_name = CICFLOWMETER_TO_CICIDS2017.get(k)
        if cicids_name:
            renamed[cicids_name] = v

    for col in feature_columns:
        if col in renamed:
            try:
                mapped[col] = float(renamed[col])
            except (ValueError, TypeError):
                mapped[col] = 0.0
        else:
            mapped[col] = 0.0
            missing.append(col)

    if missing:
        print(f"[live_agent] KUJDES: {len(missing)} features mungojne, mbushur me 0: {missing}",
              file=sys.stderr)

    return mapped


def predict_flow(model, label_encoder, feature_vector: dict, feature_columns: list):

    x = np.array([[feature_vector[col] for col in feature_columns]])
    pred_idx = model.predict(x)[0]
    pred_proba = model.predict_proba(x)[0]
    confidence = float(pred_proba[pred_idx])
    label = label_encoder.inverse_transform([pred_idx])[0]
    return label, confidence


def login_and_get_token(backend_url: str, username: str, password: str) -> str:

    resp = requests.post(f"{backend_url}/api/auth/login",
                          json={"username": username, "password": password}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("token") or data.get("accessToken")
    if not token:
        raise RuntimeError(f"Login-i u be por s'u gjet token ne pergjigje: {data}")
    return token


def ingest_flow(backend_url: str, token: str, row: dict, feature_vector: dict, label: str, confidence: float):

    payload = {
        "sourceIp": row.get("src_ip", "0.0.0.0"),
        "destinationIp": row.get("dst_ip", "0.0.0.0"),
        "sourcePort": int(float(row.get("src_port", 0) or 0)),
        "destinationPort": int(float(row.get("dst_port", 0) or 0)),
        "protocol": "TCP" if row.get("protocol") == "6" else "UDP" if row.get("protocol") == "17" else "OTHER",
        "featureVector": feature_vector,
        "predictedLabel": "BENIGN" if label == "BENIGN" else "ATTACK",
        "predictionConfidence": confidence,
        "attackType": label,
        "flowTimestamp": datetime.now(timezone.utc).isoformat(),
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.post(f"{backend_url}/api/alarms/ingest", json=payload, headers=headers, timeout=5)
        resp.raise_for_status()
        print(f"[live_agent] Ingested: {label} (conf={confidence:.4f}) "
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
    parser.add_argument("--username", default="ml-service", help="Username per login te backend")
    parser.add_argument("--password", default="ml-service-secret", help="Password per login te backend")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    print(f"[live_agent] Duke ngarkuar modelin '{args.model_file}' nga {models_dir} ...")
    model, label_encoder, feature_columns = load_model_artifacts(models_dir, args.model_file)
    print(f"[live_agent] Modeli u ngarkua. {len(feature_columns)} features, "
          f"{len(label_encoder.classes_)} klasa: {list(label_encoder.classes_)}")

    print(f"[live_agent] Duke bere login te {args.backend} si '{args.username}' ...")
    token = login_and_get_token(args.backend, args.username, args.password)
    print("[live_agent] Login i suksesshem, token i marre.")

    csv_path = Path(args.csv_out)
    if csv_path.exists():
        csv_path.unlink()

    print(f"[live_agent] Duke nisur cicflowmeter ne {args.interface} -> {csv_path} ...")
    proc = subprocess.Popen(
        ["sudo", args.cicflowmeter_path, "-i", args.interface, "-c", str(csv_path)],
    )

    seen_rows = 0
    print(f"[live_agent] Duke monitoruar {csv_path} per flow te rinj (Ctrl+C per te ndaluar) ...")
    try:
        while True:
            time.sleep(args.poll_interval)
            if not csv_path.exists():
                continue

            with open(csv_path, newline="") as f:
                reader = list(csv.DictReader(f))

            new_rows = reader[seen_rows:]
            for row in new_rows:
                feature_vector = map_row_to_feature_vector(row, feature_columns)
                label, confidence = predict_flow(model, label_encoder, feature_vector, feature_columns)
                ingest_flow(args.backend, token, row, feature_vector, label, confidence)
            seen_rows = len(reader)

    except KeyboardInterrupt:
        print("\n[live_agent] Duke ndaluar...")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
