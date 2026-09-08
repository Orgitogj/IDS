import numpy as np

from app.live import protocol
from training.pipeline import families

PROTOCOL_VERSION = protocol.PROTOCOL_VERSION
BENIGN = families.BENIGN
UNLABELLED = "UNLABELLED"

BENIGN_FPR_DEFINITION = protocol.BENIGN_FPR_DEFINITION
DETECTION_DEFINITION = protocol.DETECTION_DEFINITION
ATTRIBUTION_DEFINITION = protocol.ATTRIBUTION_DEFINITION

MIN_SUPPORT_FOR_RATE = 30


class LiveEvaluationError(RuntimeError):
    pass


def evaluable_flows(flows):
    return [flow for flow in flows
            if flow.get("validation_status") == protocol.STATUS_VALID
            and flow.get("expected_binary_label") in protocol.EXPECTED_BINARY_LABELS]


def flow_counts(flows):
    total = len(flows)
    valid = sum(1 for flow in flows
                if flow.get("validation_status") == protocol.STATUS_VALID)
    unlabelled = sum(1 for flow in flows
                     if flow.get("expected_binary_label") == UNLABELLED)
    statuses = {}
    for flow in flows:
        status = flow.get("validation_status") or protocol.STATUS_INGEST_ERROR
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "flow_count": total,
        "valid_flow_count": valid,
        "invalid_flow_count": total - valid,
        "unlabelled_flow_count": unlabelled,
        "evaluable_flow_count": len(evaluable_flows(flows)),
        "validation_status_counts": dict(sorted(statuses.items())),
    }


def _rate(numerator, denominator):
    if not denominator:
        return None
    return float(numerator / denominator)


def _support_warning(attack_flows, benign_flows):
    thin = []
    if 0 < attack_flows < MIN_SUPPORT_FOR_RATE:
        thin.append(f"attack denominator is {attack_flows}")
    if 0 < benign_flows < MIN_SUPPORT_FOR_RATE:
        thin.append(f"benign denominator is {benign_flows}")
    if not thin:
        return None
    return (f"{'; '.join(thin)} (below {MIN_SUPPORT_FOR_RATE}); report raw counts rather "
            f"than rates alone")


def binary_detection(flows):
    scored = evaluable_flows(flows)

    if not scored:
        return {"evaluable_flows": 0, "note": "no evaluable flow in this run",
                "benign_fpr_definition": BENIGN_FPR_DEFINITION,
                "detection_definition": DETECTION_DEFINITION}

    true_attack = np.array([flow["expected_binary_label"] == "ATTACK" for flow in scored])
    pred_attack = np.array([str(flow.get("predicted_label")) != BENIGN for flow in scored])

    true_positive = int((true_attack & pred_attack).sum())
    false_positive = int((~true_attack & pred_attack).sum())
    false_negative = int((true_attack & ~pred_attack).sum())
    true_negative = int((~true_attack & ~pred_attack).sum())

    attack_flows = true_positive + false_negative
    benign_flows = true_negative + false_positive
    flagged = true_positive + false_positive

    precision = _rate(true_positive, flagged)
    recall = _rate(true_positive, attack_flows)
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0

    return {
        "evaluable_flows": len(scored),
        "attack_flows": attack_flows,
        "benign_flows": benign_flows,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "attack_detection_rate": recall,
        "attack_detection_rate_denominator": attack_flows,
        "attack_miss_rate": _rate(false_negative, attack_flows),
        "attack_miss_rate_denominator": attack_flows,
        "benign_false_positive_rate": _rate(false_positive, benign_flows),
        "benign_false_positive_rate_denominator": benign_flows,
        "attack_precision": precision,
        "attack_precision_denominator": flagged,
        "attack_f1": float(f1),
        "binary_accuracy": _rate(true_positive + true_negative, len(scored)),
        "rate_support_warning": _support_warning(attack_flows, benign_flows),
        "benign_fpr_definition": BENIGN_FPR_DEFINITION,
        "detection_definition": DETECTION_DEFINITION,
    }


def attribution(flows, expected_family=None, expected_label=None):
    scored = [flow for flow in evaluable_flows(flows)
              if flow.get("expected_binary_label") == "ATTACK"]
    flagged = [str(flow.get("predicted_label")) for flow in scored
               if str(flow.get("predicted_label")) != BENIGN]

    if not flagged:
        return {
            "attack_predictions": 0,
            "scored_attack_flows": len(scored),
            "predicted_label_distribution": {},
            "predicted_family_distribution": {},
            "dominant_predicted_label": None,
            "dominant_predicted_family": None,
            "attribution_scored": False,
            "attribution_definition": ATTRIBUTION_DEFINITION,
            "note": "no ground-truth attack flow was predicted as an attack",
        }

    labels, counts = np.unique(np.array(flagged, dtype=object), return_counts=True)
    label_distribution = {str(name): int(count) for name, count in zip(labels, counts)}

    family_distribution = {}
    for name, count in label_distribution.items():
        family = families.family_of(name) or "unmapped"
        family_distribution[family] = family_distribution.get(family, 0) + count

    dominant_label = max(label_distribution.items(), key=lambda item: item[1])
    dominant_family = max(family_distribution.items(), key=lambda item: item[1])

    report = {
        "attack_predictions": len(flagged),
        "scored_attack_flows": len(scored),
        "predicted_label_distribution": dict(sorted(label_distribution.items(),
                                                    key=lambda item: -item[1])),
        "predicted_family_distribution": dict(sorted(family_distribution.items(),
                                                     key=lambda item: -item[1])),
        "dominant_predicted_label": dominant_label[0],
        "dominant_predicted_label_share": float(dominant_label[1] / len(flagged)),
        "dominant_predicted_family": dominant_family[0],
        "dominant_predicted_family_share": float(dominant_family[1] / len(flagged)),
        "attribution_definition": ATTRIBUTION_DEFINITION,
    }

    if not expected_family and not expected_label:
        report["attribution_scored"] = False
        report["note"] = ("the manifest declares no defensible CICIDS2017 mapping for this "
                          "scenario, so only binary detection is scored")
        return report

    report["attribution_scored"] = True
    report["expected_family"] = expected_family
    report["expected_label"] = expected_label

    if expected_label:
        correct = sum(count for name, count in label_distribution.items()
                      if name == expected_label)
        report["label_attribution_correct"] = correct
        report["label_attribution_rate"] = float(correct / len(flagged))
        report["label_attribution_denominator"] = len(flagged)

    if expected_family:
        correct = sum(count for name, count in family_distribution.items()
                      if name == expected_family)
        report["family_attribution_correct"] = correct
        report["family_attribution_rate"] = float(correct / len(flagged))
        report["family_attribution_denominator"] = len(flagged)

    return report


def benign_baseline(flows):
    scored = [flow for flow in evaluable_flows(flows)
              if flow.get("expected_binary_label") == "BENIGN"]

    if not scored:
        return {"valid_benign_flows": 0,
                "note": "no evaluable benign flow in this run",
                "benign_fpr_definition": BENIGN_FPR_DEFINITION}

    predicted = [str(flow.get("predicted_label")) for flow in scored]
    as_benign = sum(1 for name in predicted if name == BENIGN)
    as_attack = len(predicted) - as_benign

    false_positive_labels = {}
    for name in predicted:
        if name == BENIGN:
            continue
        false_positive_labels[name] = false_positive_labels.get(name, 0) + 1

    return {
        "valid_benign_flows": len(scored),
        "predicted_benign": as_benign,
        "predicted_attack": as_attack,
        "benign_false_positive_rate": _rate(as_attack, len(scored)),
        "benign_false_positive_rate_denominator": len(scored),
        "false_positive_label_distribution": dict(sorted(false_positive_labels.items(),
                                                         key=lambda item: -item[1])),
        "rate_support_warning": _support_warning(0, len(scored)),
        "benign_fpr_definition": BENIGN_FPR_DEFINITION,
    }


def run_report(manifest, flows, run_state):
    status = run_state.get("status")
    if status not in protocol.EVALUABLE_RUN_STATUSES:
        raise LiveEvaluationError(
            f"run {run_state.get('run_id')} ka status {status}; vetem "
            f"{protocol.EVALUABLE_RUN_STATUSES} hyjne ne evaluim")

    return {
        "schema_version": 1,
        "experiment_type": "live_lab",
        "protocol_version": PROTOCOL_VERSION,
        "experiment_id": manifest.experiment_id,
        "run_id": manifest.run_id,
        "scenario_id": manifest.scenario_id,
        "expected_binary_label": manifest.expected_binary_label,
        "smoke_test": manifest.smoke_test,
        "exclude_from_thesis_metrics": manifest.exclude_from_thesis_metrics,
        "counts": flow_counts(flows),
        "binary": binary_detection(flows),
        "attribution": attribution(flows, manifest.expected_family,
                                   manifest.expected_label),
        "benign_baseline": benign_baseline(flows),
        "run_state": run_state,
    }


def aggregate(run_reports):
    included = [report for report in run_reports
                if not report.get("exclude_from_thesis_metrics")]
    excluded = [report["run_id"] for report in run_reports
                if report.get("exclude_from_thesis_metrics")]

    return {
        "schema_version": 1,
        "experiment_type": "live_lab",
        "protocol_version": PROTOCOL_VERSION,
        "runs_included": [report["run_id"] for report in included],
        "runs_excluded": excluded,
        "n_runs": len(included),
        "scenarios": sorted({report["scenario_id"] for report in included}),
        "rows": [
            {
                "run_id": report["run_id"],
                "scenario_id": report["scenario_id"],
                "expected_binary_label": report["expected_binary_label"],
                "evaluable_flows": report["binary"].get("evaluable_flows", 0),
                "attack_detection_rate": report["binary"].get("attack_detection_rate"),
                "attack_detection_rate_denominator": report["binary"].get(
                    "attack_detection_rate_denominator"),
                "benign_false_positive_rate": report["binary"].get(
                    "benign_false_positive_rate"),
                "benign_false_positive_rate_denominator": report["binary"].get(
                    "benign_false_positive_rate_denominator"),
                "dominant_predicted_label": report["attribution"].get(
                    "dominant_predicted_label"),
                "attribution_scored": report["attribution"].get("attribution_scored"),
            }
            for report in included
        ],
        "benign_fpr_definition": BENIGN_FPR_DEFINITION,
        "detection_definition": DETECTION_DEFINITION,
        "attribution_definition": ATTRIBUTION_DEFINITION,
    }
