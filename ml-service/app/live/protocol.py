PROTOCOL_VERSION = "live-lab-v1"
EXPERIMENT_ID = "lab-generalization-v1"

FROZEN_PRIMARY_MODEL = {
    "name": "xgb-baseline-cicids2017-v2",
    "version": "2.0",
    "artifact_file": "xgb_baseline_cicids2017_v2.joblib",
    "artifact_sha256": "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa",
    "feature_version": "cicids2017-78-v1",
    "n_features": 78,
    "source": "reports/artifact_evaluation/xgb_baseline_cicids2017_v2/metrics.json",
    "note": ("Pre-specified before any laboratory traffic was generated. No retraining, no "
             "threshold tuning and no model selection may follow the observation of "
             "laboratory results."),
}

EXTRA_FEATURE_POLICY = "ignore"
EXTRA_FEATURE_POLICY_NOTE = (
    "Columns present in the mapped flow but absent from the frozen feature schema are "
    "counted and reported, then dropped. They never reach the model and never change the "
    "vector, because the vector is projected in frozen schema order. Set the policy to "
    "'reject' to fail closed on them instead.")

STATUS_VALID = "VALID"
STATUS_INVALID_SCHEMA = "INVALID_SCHEMA"
STATUS_MISSING_FEATURE = "MISSING_FEATURE"
STATUS_EXTRA_FEATURE = "EXTRA_FEATURE"
STATUS_NONFINITE_VALUE = "NONFINITE_VALUE"
STATUS_MODEL_ERROR = "MODEL_ERROR"
STATUS_INGEST_ERROR = "INGEST_ERROR"

VALIDATION_STATUSES = [
    STATUS_VALID, STATUS_INVALID_SCHEMA, STATUS_MISSING_FEATURE, STATUS_EXTRA_FEATURE,
    STATUS_NONFINITE_VALUE, STATUS_MODEL_ERROR, STATUS_INGEST_ERROR,
]

VALIDATION_STATUS_NOTE = (
    "validationStatus describes pipeline and data integrity only. A flow the classifier "
    "labels incorrectly is still VALID; prediction correctness is never a validation "
    "outcome.")

RUN_PLANNED = "PLANNED"
RUN_RUNNING = "RUNNING"
RUN_COMPLETED = "COMPLETED"
RUN_ABORTED = "ABORTED"
RUN_INVALID = "INVALID"

RUN_STATUSES = [RUN_PLANNED, RUN_RUNNING, RUN_COMPLETED, RUN_ABORTED, RUN_INVALID]
EVALUABLE_RUN_STATUSES = [RUN_COMPLETED]

EXPECTED_BINARY_LABELS = ["BENIGN", "ATTACK"]

BENIGN_FPR_DEFINITION = (
    "fraction of true BENIGN flows predicted as some attack class - identical to the "
    "definition used by random-v2 (overall_metrics.binary_benign_vs_attack), by the "
    "corrected temporal evaluation and by lofo-v1. It is NOT the per-class BENIGN fpr and "
    "NOT attack_rows_predicted_as_benign_rate.")

DETECTION_DEFINITION = (
    "attack_detection_rate is the fraction of ground-truth ATTACK flows predicted as ANY "
    "non-BENIGN class. It says the traffic was flagged as malicious; it says nothing about "
    "whether the assigned CICIDS2017 label was correct. Attribution is reported "
    "separately.")

ATTRIBUTION_DEFINITION = (
    "Attribution is only scored when the laboratory scenario declares a defensible mapping "
    "to a CICIDS2017 label or family. Where the manifest declares no mapping, binary "
    "detection is reported and attribution is left unscored rather than guessed.")

CAPTURE_TIME_EXACT = "cicflowmeter_flow_timestamp"
CAPTURE_TIME_APPROX_INGEST = "approximate_agent_read_time"

CAPTURE_TIME_SOURCES = [CAPTURE_TIME_EXACT, CAPTURE_TIME_APPROX_INGEST]

CAPTURE_TIME_NOTE = (
    "captureTimestamp is the time the flow was observed on the wire, taken from the "
    "CICFlowMeter timestamp column. ingestedAt is when the record reached the agent or the "
    "backend. They are stored separately and neither is ever written over the other. When "
    "the capture column is unusable the timestamp is marked "
    "approximate_agent_read_time and is NOT presented as a packet-capture time.")

LATENCY_MODEL_INFERENCE = "model_inference_latency"
LATENCY_PRODUCTION_PATH = "production_path_inference_latency"
LATENCY_END_TO_END = "end_to_end_IDS_latency"

LATENCY_LAYER_NOTE = (
    "model_inference_latency covers predict() on an input-ready vector. "
    "production_path_inference_latency adds mapping, validation and DataFrame "
    "construction. end_to_end_IDS_latency additionally covers capture, Spring ingest and "
    "persistence, and may only be reported once every one of those components has been "
    "measured. SHAP and LLM explanation are separate layers and are excluded from all "
    "three.")
