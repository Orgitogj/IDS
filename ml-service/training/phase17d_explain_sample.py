import csv
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.services import llm_explainer
from training.build_adaptation_dataset import adaptation_manifest
from training.build_final_eval_dataset import SCENARIO_OF

PHASE17D = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17d"
CAPTURES = PHASE17D / "captures"
OUT = PHASE17D / "llm_explainability"
PHASE17C = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17c"
MODEL_B = _ML_SERVICE_ROOT / "models" / "model_b" / "model_b_xgb_weighted_v1.joblib"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"

SEED = 42
TOP_K = 5
THRESHOLD = 0.50
N_PER_STRATUM = 6
PORTSCAN_POOL = 2000
PORTSCAN_RUN = "eval-v1-portscan-001"
BENIGN_RUNS = ["eval-v1-benign-001", "eval-v1-benign-002", "eval-v1-benign-003"]


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def prompt_template_hash():
    blocks = "\n".join([
        llm_explainer.PROMPT_VERSION,
        llm_explainer.ROLE,
        llm_explainer.EVIDENCE_BOUNDARY,
        llm_explainer.INVENTION_RULES,
        llm_explainer.STYLE_RULES,
    ])
    return sha256_bytes(blocks.encode("utf-8"))


def features_b():
    c = json.loads((PHASE17C / "protocol.json").read_text(encoding="utf-8"))
    return c["feature_contract"]["feature_list"]


def to_matrix(rows, feats):
    frame = pd.DataFrame(rows, columns=feats).apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return frame[feats].to_numpy(dtype=np.float64)


def selector_match(row):
    return str(row.get("src_ip")) == "192.168.50.10" and \
        str(row.get("dst_ip")) == "192.168.50.20"


def shap_package(model, booster, feats, vec, run_id, flow_index):
    x = vec.reshape(1, -1)
    started = time.perf_counter()
    contribs = booster.predict(xgb.DMatrix(x), pred_contribs=True)[0]
    shap_latency_ms = (time.perf_counter() - started) * 1000.0
    proba = float(model.predict_proba(x)[0, 1])
    base_value = float(contribs[-1])
    feat_contribs = contribs[:-1]
    order = sorted(range(len(feats)), key=lambda i: abs(feat_contribs[i]), reverse=True)
    top = []
    for i in order[:TOP_K]:
        s = float(feat_contribs[i])
        top.append({
            "feature": feats[i],
            "value": float(vec[i]),
            "shap_contribution": s,
            "direction": "increases_attack" if s > 0 else "decreases_attack",
        })
    decision = "ATTACK" if proba >= THRESHOLD else "BENIGN"
    package = {
        "alert_id": f"{run_id}#{flow_index}",
        "source_run": run_id,
        "flow_index": flow_index,
        "model": {
            "id": "model-b-xgb-weighted-v1",
            "sha256": MODEL_B_SHA,
            "feature_schema": "deployment-cicflowmeter-76-v1",
            "threshold": THRESHOLD,
        },
        "decision": decision,
        "attack_probability": proba,
        "shap_base_value": base_value,
        "top_shap_features": top,
        "analyst_instruction": ("Explain only the model decision from the evidence below; "
                                "do not invent packet contents, identities, protocols, "
                                "attack tools or causes not present in this evidence."),
    }
    return package, shap_latency_ms, decision, proba


def iter_rows(run_id):
    with open(CAPTURES / f"{run_id}.csv", newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            yield i, row


def build():
    feats = features_b()
    model = joblib.load(MODEL_B)
    booster = model.get_booster()
    rng = random.Random(SEED)

    benign_fp = []
    for run_id in BENIGN_RUNS:
        idxs, vecs = [], []
        for i, row in iter_rows(run_id):
            idxs.append(i)
            vecs.append([row.get(c) for c in feats])
        proba = model.predict_proba(to_matrix(vecs, feats))[:, 1]
        for k, p in zip(idxs, proba):
            if p >= THRESHOLD:
                benign_fp.append((run_id, k))
    benign_fp.sort()
    benign_pick = sorted(rng.sample(benign_fp, min(N_PER_STRATUM, len(benign_fp))))

    portscan_pool = []
    for i, row in iter_rows(PORTSCAN_RUN):
        mani = adaptation_manifest("portscan", PORTSCAN_RUN)
        if selector_match(row) and mani.expected_for_flow(row) == "ATTACK":
            portscan_pool.append((i, [row.get(c) for c in feats]))
        if len(portscan_pool) >= PORTSCAN_POOL:
            break
    ps_indices = sorted(rng.sample(range(len(portscan_pool)),
                                   min(N_PER_STRATUM, len(portscan_pool))))
    portscan_pick = [portscan_pool[j] for j in ps_indices]

    def row_vector(run_id, flow_index):
        for i, row in iter_rows(run_id):
            if i == flow_index:
                return to_matrix([[row.get(c) for c in feats]], feats)[0]
        raise SystemExit(f"row {flow_index} not found in {run_id}")

    packages = []
    manifest_items = []
    latencies = []

    for (run_id, flow_index) in benign_pick:
        vec = row_vector(run_id, flow_index)
        pkg, lat, decision, proba = shap_package(model, booster, feats, vec,
                                                 run_id, flow_index)
        packages.append(pkg)
        latencies.append(lat)
        manifest_items.append({
            "alert_id": pkg["alert_id"], "source_run": run_id,
            "flow_index": flow_index, "scenario": SCENARIO_OF[run_id],
            "model_b_decision": decision, "model_b_attack_probability": proba,
            "ground_truth_binary": "BENIGN",
            "stratum": "benign_false_positive_alert",
            "inclusion_reason": "benign flow that frozen Model B flagged as ATTACK "
                                "(operational false-positive alert)",
        })

    for (flow_index, _vals) in portscan_pick:
        vec = row_vector(PORTSCAN_RUN, flow_index)
        pkg, lat, decision, proba = shap_package(model, booster, feats, vec,
                                                 PORTSCAN_RUN, flow_index)
        packages.append(pkg)
        latencies.append(lat)
        manifest_items.append({
            "alert_id": pkg["alert_id"], "source_run": PORTSCAN_RUN,
            "flow_index": flow_index, "scenario": "portscan",
            "model_b_decision": decision, "model_b_attack_probability": proba,
            "ground_truth_binary": "ATTACK",
            "stratum": "correctly_detected_attack_alert",
            "inclusion_reason": "PortScan attack flow correctly flagged as ATTACK by "
                                "frozen Model B (true-positive alert)",
        })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence_sample.json").write_text(
        json.dumps({"schema_version": 1, "generated_at": utc_now(),
                    "packages": packages}, indent=1) + "\n", encoding="utf-8")

    lat_sorted = sorted(latencies)
    n = len(lat_sorted)
    median = lat_sorted[n // 2] if n else None
    manifest = {
        "schema_version": 1,
        "protocol_version": "phase17d-explainability-v1",
        "generated_at": utc_now(),
        "seed": SEED,
        "top_k": TOP_K,
        "threshold": THRESHOLD,
        "model_id": "model-b-xgb-weighted-v1",
        "model_sha256": MODEL_B_SHA,
        "feature_schema": "deployment-cicflowmeter-76-v1",
        "prompt_template_version": llm_explainer.PROMPT_VERSION,
        "prompt_template_sha256": prompt_template_hash(),
        "sampling_rule": (
            f"deterministic, seed {SEED}: {N_PER_STRATUM} benign false-positive alerts "
            f"sampled from all benign flows Model B flagged ATTACK across "
            f"{','.join(BENIGN_RUNS)}; {N_PER_STRATUM} true-positive PortScan alerts "
            f"sampled from the first {PORTSCAN_POOL} selector-matched evaluable flows of "
            f"{PORTSCAN_RUN}. Ground truth from manifest selectors; NOT included in the "
            f"evidence packages given to the LLM."),
        "n_benign_false_positive_alerts": len(benign_pick),
        "n_true_positive_attack_alerts": len(portscan_pick),
        "n_total": len(manifest_items),
        "benign_false_positive_pool_size": len(benign_fp),
        "shap_latency_ms": {"n": n, "median": median,
                            "min": (lat_sorted[0] if n else None),
                            "max": (lat_sorted[-1] if n else None)},
        "items": manifest_items,
    }
    (OUT / "sample_manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    print(f"benign_fp_pool={len(benign_fp)} benign_pick={len(benign_pick)} "
          f"portscan_pick={len(portscan_pick)} total={len(manifest_items)}")
    print(f"prompt_template_sha256={manifest['prompt_template_sha256']}")
    print(f"shap_latency_ms median={median}")
    return manifest


if __name__ == "__main__":
    build()
