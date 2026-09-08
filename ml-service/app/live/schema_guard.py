import math

from app.live import protocol


class SchemaViolation(Exception):
    def __init__(self, status, errors):
        self.status = status
        self.errors = list(errors)
        super().__init__(f"{status}: {'; '.join(self.errors)}")


def check_schema(feature_columns, expected_names, expected_count=None):
    errors = []
    columns = [str(name) for name in feature_columns]
    expected = [str(name) for name in expected_names]

    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate feature columns: {', '.join(duplicates)}")

    if expected_count is not None and len(columns) != expected_count:
        errors.append(f"feature count {len(columns)} does not match the frozen "
                      f"schema count {expected_count}")

    if len(columns) != len(expected):
        errors.append(f"feature count {len(columns)} does not match the reference "
                      f"schema length {len(expected)}")

    missing = [name for name in expected if name not in columns]
    if missing:
        errors.append(f"{len(missing)} feature(s) absent from the model schema: "
                      f"{', '.join(missing[:5])}")

    extra = [name for name in columns if name not in expected]
    if extra:
        errors.append(f"{len(extra)} feature(s) not present in the frozen schema: "
                      f"{', '.join(extra[:5])}")

    if not missing and not extra and columns != expected:
        first = next(i for i, (a, b) in enumerate(zip(columns, expected)) if a != b)
        errors.append(f"feature order diverges at position {first}: "
                      f"model has '{columns[first]}', schema has '{expected[first]}'")

    return {
        "schema_validation_status": (protocol.STATUS_VALID if not errors
                                     else protocol.STATUS_INVALID_SCHEMA),
        "feature_schema": None,
        "feature_count": len(columns),
        "errors": errors,
    }


def assert_schema(feature_columns, expected_names, feature_schema, expected_count=None):
    report = check_schema(feature_columns, expected_names, expected_count)
    report["feature_schema"] = feature_schema
    if report["errors"]:
        raise SchemaViolation(report["schema_validation_status"], report["errors"])
    return report


def status_from_validation(validation, extra_feature_policy=None):
    policy = extra_feature_policy or protocol.EXTRA_FEATURE_POLICY
    errors = []

    missing = list(getattr(validation, "missing_features", []) or [])
    invalid = list(getattr(validation, "invalid_features", []) or [])
    extra = list(getattr(validation, "unexpected_features", []) or [])

    nonfinite = [entry for entry in invalid
                 if str(entry.get("reason")) in ("nan", "inf")]
    other_invalid = [entry for entry in invalid if entry not in nonfinite]

    if missing:
        errors.append(f"{len(missing)} missing: {', '.join(str(f) for f in missing[:5])}")
    for entry in nonfinite[:5]:
        errors.append(f"{entry.get('feature')}: {entry.get('reason')}")
    for entry in other_invalid[:5]:
        errors.append(f"{entry.get('feature')}: {entry.get('reason')}")

    if missing:
        status = protocol.STATUS_MISSING_FEATURE
    elif nonfinite:
        status = protocol.STATUS_NONFINITE_VALUE
    elif other_invalid:
        status = protocol.STATUS_INVALID_SCHEMA
    elif extra and policy == "reject":
        status = protocol.STATUS_EXTRA_FEATURE
        errors.append(f"{len(extra)} unexpected feature(s): "
                      f"{', '.join(str(f) for f in extra[:5])}")
    else:
        status = protocol.STATUS_VALID

    return {
        "validation_status": status,
        "validation_errors": errors[:10],
        "extra_features_ignored": len(extra) if policy == "ignore" else 0,
        "extra_feature_policy": policy,
    }


def assert_finite_vector(vector):
    bad = [index for index, value in enumerate(vector)
           if value is None or not math.isfinite(float(value))]
    if bad:
        raise SchemaViolation(protocol.STATUS_NONFINITE_VALUE,
                              [f"non-finite value at feature index {index}"
                               for index in bad[:5]])
    return True
