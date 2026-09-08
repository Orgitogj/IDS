import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import domain_adaptation as da

OUT_DIR = _ML_SERVICE_ROOT / "reports" / "domain_adaptation"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def feasibility():
    return {
        "schema_version": 1,
        "protocol_version": da.PROTOCOL_VERSION,
        "generated_at": utc_now(),
        "design_only": True,
        "no_training": True, "no_traffic": True, "no_shap": True, "no_llm": True,
        "strategy_a_common_extractor": {
            "concept": ("re-extract original CICIDS2017 PCAPs with python cicflowmeter "
                        "0.5.0 so training and deployment share one extractor"),
            "local_cicids2017_pcaps": False,
            "what_is_local": ("published Java-CICFlowMeter flow CSVs "
                              "(datasets/MachineLearningCVE, datasets/TrafficLabelling) "
                              "and the derived cicids2017_cleaned.parquet"),
            "raw_pcap_size_estimate_gb": "~50 (5 capture days, official UNB distribution)",
            "disk_free_gb": 640,
            "blockers": [
                "original raw PCAPs are not local and must be downloaded from the "
                "official UNB source (~50 GB)",
                "python cicflowmeter would segment flows differently from the original "
                "Java extractor, so the original flow-level labels do not map 1:1 to "
                "re-extracted flows (a non-trivial label-transfer / flow-matching "
                "problem with real leakage risk)",
                "full re-extraction of 5 days is long-running and unverified for label "
                "fidelity",
            ],
            "feasible_now": False,
            "feasible_in_principle": True,
            "verdict": "IMPRACTICAL_NOW_DOCUMENTED_AS_FUTURE_WORK",
        },
        "strategy_b_lab_domain_adaptation": {
            "concept": ("train Model B on laboratory flows extracted with python "
                        "cicflowmeter 0.5.0 and evaluate on NEW laboratory runs extracted "
                        "the same way; train and deployment share the extractor by "
                        "construction"),
            "data_available": ("existing lab runs (benign 5407, portscan 1362 ATTACK, "
                               "ssh 69 ATTACK) plus new runs generated later"),
            "same_extractor_train_and_deploy": True,
            "limitation": ("fixes extractor-consistency AND domain-match simultaneously, "
                           "so it answers the mitigation question but does not isolate "
                           "the extractor effect alone"),
            "feasible_now": True,
            "verdict": "PRACTICAL_RECOMMENDED",
        },
        "recommended_strategy": "B",
        "recommended_strategy_reason": (
            "Strategy A needs ~50 GB of non-local PCAPs and an unsolved label-transfer "
            "problem; Strategy B is practical now, shares the extractor between training "
            "and deployment, and directly tests whether the deployment gap shrinks when "
            "the feature-extraction environment is consistent. Strategy A is retained as "
            "future work that would additionally isolate the extractor effect."),
    }


def strategy_comparison_rows():
    return [
        {"strategy": "A common-extractor (re-extract CICIDS2017 with python cfm)",
         "extractor_consistency": "train+deploy share python cfm",
         "isolates_extractor_effect": "yes",
         "data_needed": "~50 GB official PCAPs (not local)",
         "leakage_risk": "label-transfer across re-segmented flows",
         "effort": "very high", "feasible_now": "no",
         "recommendation": "future work"},
        {"strategy": "B lab-domain adaptation (train on lab python-cfm flows)",
         "extractor_consistency": "train+deploy share python cfm",
         "isolates_extractor_effect": "no (also matches domain)",
         "data_needed": "existing + new lab runs (local)",
         "leakage_risk": "run-level separation required",
         "effort": "moderate", "feasible_now": "yes",
         "recommendation": "PRIMARY"},
    ]


def data_split_protocol():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "separation": "RUN_LEVEL_ONLY",
        "rule": ("no flow from an adaptation or validation run may appear in the final "
                 "Model-B test partition; splitting is by whole run, never by random "
                 "flow"),
        "roles": da.RUN_ROLES,
        "existing_lab_runs": {
            "lab-v1-benign-001": "adaptation (Model B); Model A result stays frozen",
            "lab-v1-portscan-001": "adaptation (Model B); Model A result stays frozen",
            "lab-v1-ssh-bruteforce-001": ("adaptation (Model B); too few flows (69) to "
                                          "split, used whole for adaptation"),
        },
        "final_test": ("only NEW runs generated AFTER Model B is frozen; never any "
                       "existing run"),
        "calibration": ("learned only from a validation slice of adaptation runs, never "
                        "from final test"),
    }


def run_plan():
    runs = []
    for scen in ("benign", "portscan", "ssh"):
        runs.append({"run_id": f"lab-v1-{scen if scen!='ssh' else 'ssh-bruteforce'}-001",
                     "scenario": scen, "role": da.ADAPTATION,
                     "source": "existing accepted Model-A run, reused as adaptation only",
                     "generated_after_model_b_freeze": False})
    for scen in ("benign", "portscan", "ssh"):
        for n in (2, 3, 4):
            runs.append({"run_id": f"adapt-v1-{scen}-{n:03d}", "scenario": scen,
                         "role": da.ADAPTATION,
                         "source": "new adaptation run (different session/time window)",
                         "generated_after_model_b_freeze": False})
    for scen in ("benign", "portscan", "ssh"):
        for n in (1, 2, 3):
            runs.append({"run_id": f"eval-v1-{scen}-{n:03d}", "scenario": scen,
                         "role": da.FINAL_TEST,
                         "source": "new unseen run generated AFTER Model B freeze",
                         "generated_after_model_b_freeze": True})
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "replication": {
            "adaptation_runs_per_scenario": ">=3 (incl. reused existing where available)",
            "final_test_runs_per_scenario": ">=3",
            "different_sessions_time_windows": True,
            "no_prediction_driven_repetition": True,
            "min_valid_flow_support_per_eval_run": {"benign": 300, "portscan": 300,
                                                    "ssh": 30},
            "report_run_level_variability": ["mean", "median", "range", "std"],
        },
        "runs": runs,
    }


def model_b_options():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "options": [
            {"option": "A", "model": "binary XGBoost deployment detector",
             "data": "lab python-cfm adaptation flows", "leakage_risk": "low (run-level)",
             "advantage": "direct binary objective; comparable pipeline to Model A",
             "disadvantage": "lab-specific", "fairness_vs_model_a": "paired same-flow eval",
             "effort": "moderate", "recommended": True},
            {"option": "B", "model": "binary Random Forest",
             "data": "same", "leakage_risk": "low",
             "advantage": "robustness comparison to XGBoost",
             "disadvantage": "second model to maintain",
             "fairness_vs_model_a": "paired", "effort": "low", "recommended": True},
            {"option": "C", "model": "fine-tune existing XGB (Model A)",
             "data": "lab flows", "leakage_risk": "medium",
             "advantage": "reuses learned structure",
             "disadvantage": ("catastrophic forgetting; unfair comparison; mutates the "
                              "frozen benchmark lineage"),
             "fairness_vs_model_a": "poor", "effort": "medium", "recommended": False},
            {"option": "D", "model": "new model on common-extractor CICIDS2017",
             "data": "Strategy A (~50 GB pcaps)", "leakage_risk": "label-transfer",
             "advantage": "isolates extractor effect",
             "disadvantage": "not feasible now", "fairness_vs_model_a": "strong if done",
             "effort": "very high", "recommended": False},
            {"option": "E", "model": "two-stage: binary detector + frozen Model A attrib",
             "data": "lab flows for stage 1", "leakage_risk": "low",
             "advantage": ("keeps Model A frozen; no forgetting; ground-truth compatible; "
                           "full comparability"),
             "disadvantage": "two components; slightly higher latency",
             "fairness_vs_model_a": "strong", "effort": "moderate", "recommended": True},
        ],
        "recommendation": ("Option E architecture (two-stage) with Option A binary "
                           "XGBoost as the Stage-1 detector and Option B RF as a "
                           "robustness check; Stage 2 = frozen Model A for attribution"),
        "two_stage_rationale": {
            "keeps_model_a_frozen": True,
            "catastrophic_forgetting_risk": "eliminated (Model A untouched)",
            "ground_truth_compatibility": "binary stage matches lab binary ground truth",
            "latency": "stage 2 runs only on flows stage 1 flags as malicious",
            "interpretability": "stage 1 decision + stage 2 attribution reported separately",
            "comparability_with_model_a": "paired same-flow evaluation",
        },
    }


def balancing_strategy():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "applies_to": "adaptation/training data ONLY; never final test",
        "current_imbalance": {"benign": 5407, "portscan_attack": 1362, "ssh_attack": 69},
        "options_ranked": [
            {"method": "class_weights (scale_pos_weight)", "preferred": True,
             "reason": "no synthetic data; robust; recommended primary"},
            {"method": "controlled_undersampling_benign", "preferred": False,
             "reason": "comparison baseline; discards benign data"},
            {"method": "oversampling_minority", "preferred": False,
             "reason": "risk of overfitting the few ssh flows"},
            {"method": "SMOTE", "preferred": False,
             "reason": ("not assumed beneficial; random-v2 showed SMOTE is not "
                        "universally helpful; only if independently justified for flow "
                        "features")},
        ],
        "test_distribution": "never altered",
    }


def evaluation_protocol():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "pre_registered": True,
        "primary": ["attack_detection_rate_recall", "benign_false_positive_rate",
                    "binary_macro_f1"],
        "secondary": ["binary_precision", "binary_accuracy", "per_run_detection",
                      "confidence_distribution", "family_attribution_where_defensible"],
        "every_rate_reports_denominator": True,
        "benign_fpr_definition": ("fraction of true BENIGN flows predicted ATTACK; "
                                  "identical to random-v2 / temporal / lofo / live"),
        "paired_comparison": {
            "mandatory": True,
            "procedure": ("each final eval run: one raw capture -> same python cfm "
                          "extraction -> Model A prediction AND Model B prediction on the "
                          "identical flows"),
            "forbidden": ("comparing Model A old-run metrics against Model B new-run "
                          "metrics as the primary adaptation claim"),
        },
        "model_b_success_criteria": (
            "a defensible, pre-registered comparison against Model A on identical new "
            "flows; Model B is NOT required to win, only to be measured fairly"),
        "thresholds": "fixed before viewing final results; never tuned on final test",
    }


def leakage_guards():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "guards": [
            "run-level separation (no shared run across adaptation/validation/final_test)",
            "unique run IDs enforced",
            "no adaptation/validation run in the final test partition",
            "no final-test labels used in tuning or calibration",
            "no threshold optimization on final test",
            "no feature scaler/statistic fitted on final test",
            "no prediction-based row deletion",
            "no failed run silently overwritten (aborted/invalid runs retained)",
            "frozen Model A hash pinned; Model B hash pinned once frozen",
            "feature-schema pinned",
            "extractor version pinned (cicflowmeter 0.5.0)",
        ],
        "enforced_by": "training/pipeline/domain_adaptation.py validators + tests",
    }


def calibration_ood():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "status": "design only; not executed",
        "motivation": ("SSH experiment: all attacks predicted BENIGN at confidence ~1.0; "
                       "a reliability track is warranted"),
        "components": [
            "probability calibration (Platt/isotonic) learned on validation only",
            "out-of-distribution score",
            "UNKNOWN/SUSPICIOUS rejection state",
            "existing Isolation Forest anomaly detector as a separate signal",
        ],
        "kept_separate_from_primary_supervised_detection": True,
        "no_silent_threshold_changes": True,
        "parameters_learned_from": "adaptation/validation only, never final test",
    }


def reproducibility():
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "pins": {
            "extractor": da.EXTRACTOR,
            "feature_schema": "cicids2017-78-v1 (or a documented deployment schema)",
            "model_a": da.MODEL_A, "model_b": da.MODEL_B,
            "random_seeds": "fixed and recorded per training run",
            "manifests": ["run manifests", "adaptation dataset manifest",
                          "final evaluation manifest"],
            "raw_capture_hashes": "SHA256 per capture",
            "model_cards": "one per model (A frozen, B when created)",
            "environment_versions": "python/numpy/sklearn/xgboost/cicflowmeter recorded",
        },
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan = run_plan()
    da.validate(plan, historical_run_ids=[
        "lab-v1-benign-001", "lab-v1-portscan-001", "lab-v1-ssh-bruteforce-001"])

    artifacts = {
        "feasibility.json": feasibility(),
        "data_split_protocol.json": data_split_protocol(),
        "run_plan.json": plan,
        "model_b_options.json": model_b_options(),
        "evaluation_protocol.json": evaluation_protocol(),
        "leakage_guards.json": leakage_guards(),
        "calibration_ood.json": calibration_ood(),
        "reproducibility.json": reproducibility(),
        "balancing_strategy.json": balancing_strategy(),
    }
    for name, payload in artifacts.items():
        with open(OUT_DIR / name, "w", encoding="utf-8") as h:
            json.dump(payload, h, indent=1)

    rows = strategy_comparison_rows()
    with open(OUT_DIR / "strategy_comparison.csv", "w", newline="",
              encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    n_adapt = sum(1 for r in plan["runs"] if r["role"] == da.ADAPTATION)
    n_test = sum(1 for r in plan["runs"] if r["role"] == da.FINAL_TEST)
    print(f"protocol: {da.PROTOCOL_VERSION}")
    print(f"recommended strategy: B (lab-domain adaptation)")
    print(f"run plan validated: adaptation={n_adapt} final_test={n_test}")
    print(f"artifacts written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
