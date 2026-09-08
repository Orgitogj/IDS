PROTOCOL_VERSION = "domain-adaptation-design-v1"

MODEL_A = {
    "id": "xgb-baseline-cicids2017-v2",
    "role": "frozen benchmark model",
    "artifact_sha256": "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa",
    "feature_schema": "cicids2017-78-v1",
    "status": "permanently frozen; never overwritten",
}

MODEL_B = {
    "id": "deployment-adapted-v1",
    "role": "deployment-adapted model (to be designed and, later, trained)",
    "status": "not created; design only",
}

OBJECTIVE_PRIMARY = "binary_attack_detection"
OBJECTIVE_SECONDARY = "family_attribution_where_defensible"
OBJECTIVE_TERTIARY = "exact_cicids2017_label_only_when_independently_justified"

ADAPTATION = "adaptation"
VALIDATION = "validation"
FINAL_TEST = "final_test"
RUN_ROLES = [ADAPTATION, VALIDATION, FINAL_TEST]

EXTRACTOR = {"name": "cicflowmeter", "version": "0.5.0",
             "note": "same extractor for adaptation and deployment by construction"}


class DomainAdaptationError(ValueError):
    pass


def validate_run_plan(run_plan):
    runs = run_plan.get("runs", [])
    if not runs:
        raise DomainAdaptationError("run_plan bosh")

    ids = [r["run_id"] for r in runs]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise DomainAdaptationError(f"run_id te dyfishuar: {dupes}")

    for r in runs:
        if r["role"] not in RUN_ROLES:
            raise DomainAdaptationError(f"rol i panjohur: {r['role']} ({r['run_id']})")

    return True


def assert_run_level_separation(run_plan):
    by_role = {role: {r["run_id"] for r in run_plan["runs"] if r["role"] == role}
               for role in RUN_ROLES}

    overlap_af = by_role[ADAPTATION] & by_role[FINAL_TEST]
    if overlap_af:
        raise DomainAdaptationError(
            f"run(s) ne adaptation DHE final_test: {sorted(overlap_af)}")
    overlap_vf = by_role[VALIDATION] & by_role[FINAL_TEST]
    if overlap_vf:
        raise DomainAdaptationError(
            f"run(s) ne validation DHE final_test: {sorted(overlap_vf)}")
    return True


def assert_final_test_is_post_freeze(run_plan):
    for r in run_plan["runs"]:
        if r["role"] == FINAL_TEST and not r.get("generated_after_model_b_freeze"):
            raise DomainAdaptationError(
                f"final_test run '{r['run_id']}' duhet te gjenerohet PAS ngrirjes se "
                f"Model B")
    return True


def historical_runs_not_in_final_test(run_plan, historical_run_ids):
    final = {r["run_id"] for r in run_plan["runs"] if r["role"] == FINAL_TEST}
    leaked = final & set(historical_run_ids)
    if leaked:
        raise DomainAdaptationError(
            f"run historik i Model A perdoret si final_test i Model B: {sorted(leaked)}")
    return True


def validate(run_plan, historical_run_ids=()):
    validate_run_plan(run_plan)
    assert_run_level_separation(run_plan)
    assert_final_test_is_post_freeze(run_plan)
    historical_runs_not_in_final_test(run_plan, historical_run_ids)
    return True
