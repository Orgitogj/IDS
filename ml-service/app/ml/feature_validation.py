import json
import math
from pathlib import Path

try:
    from app.replay.feature_derivation import DERIVATIONS
    from app.replay.feature_mapping import CONST_ZERO_IN_TRAINING
except ImportError:
    from feature_derivation import DERIVATIONS
    from feature_mapping import CONST_ZERO_IN_TRAINING

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_REFERENCE_PATH = _ML_SERVICE_ROOT / "reports" / "training_feature_reference.json"

REASON_MISSING = "missing"
REASON_NULL = "null"
REASON_EMPTY = "empty"
REASON_NON_NUMERIC = "non_numeric"
REASON_NAN = "nan"
REASON_INF = "inf"

_UNPARSEABLE_TEXT = {"", "nan", "none", "null", "na", "n/a", "-"}


class FeatureValidationError(Exception):
    def __init__(self, result):
        super().__init__(result.summary())
        self.result = result


class FeatureVersionMismatch(Exception):
    def __init__(self, report):
        super().__init__(report["message"])
        self.report = report


class ValidationPolicy:
    def __init__(self, name, reject_on_missing=True, reject_on_invalid=True,
                 allow_derivation=True, allow_const_zero_fill=True, range_check=True):
        self.name = name
        self.reject_on_missing = reject_on_missing
        self.reject_on_invalid = reject_on_invalid
        self.allow_derivation = allow_derivation
        self.allow_const_zero_fill = allow_const_zero_fill
        self.range_check = range_check


STRICT_POLICY = ValidationPolicy("strict")
PERMISSIVE_POLICY = ValidationPolicy("permissive", reject_on_missing=False,
                                     reject_on_invalid=False)


class FeatureValidationResult:
    def __init__(self, feature_version, policy_name):
        self.feature_version = feature_version
        self.policy = policy_name
        self.valid = True
        self.vector = None
        self.missing_features = []
        self.invalid_features = []
        self.derived_features = []
        self.zero_filled_features = []
        self.out_of_range_features = []
        self.unexpected_features = []
        self.warnings = []

    def summary(self):
        parts = []
        if self.missing_features:
            parts.append(f"{len(self.missing_features)} missing")
        if self.invalid_features:
            parts.append(f"{len(self.invalid_features)} invalid")
        if self.derived_features:
            parts.append(f"{len(self.derived_features)} derived")
        if self.zero_filled_features:
            parts.append(f"{len(self.zero_filled_features)} zero-filled")
        if self.out_of_range_features:
            parts.append(f"{len(self.out_of_range_features)} out of range")
        return ", ".join(parts) if parts else "clean"

    def to_dict(self):
        return {
            "valid": self.valid,
            "feature_version": self.feature_version,
            "policy": self.policy,
            "missing_features": list(self.missing_features),
            "invalid_features": list(self.invalid_features),
            "derived_features": list(self.derived_features),
            "zero_filled_features": list(self.zero_filled_features),
            "out_of_range_features": list(self.out_of_range_features),
            "unexpected_feature_count": len(self.unexpected_features),
            "warnings": list(self.warnings),
        }


def _parse(raw):
    if raw is None:
        return None, REASON_NULL
    if isinstance(raw, bool):
        return float(raw), None
    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str(raw).strip()
        if text.lower() in _UNPARSEABLE_TEXT:
            return None, REASON_EMPTY
        try:
            number = float(text)
        except (TypeError, ValueError):
            return None, REASON_NON_NUMERIC
    if math.isnan(number):
        return None, REASON_NAN
    if math.isinf(number):
        return None, REASON_INF
    return number, None


def load_reference(path=None):
    reference_path = Path(path) if path else DEFAULT_REFERENCE_PATH
    if not reference_path.exists():
        return None
    with open(reference_path, encoding="utf-8") as handle:
        return json.load(handle)


def verify_feature_version(feature_columns, feature_version, reference):
    if not feature_version or not reference:
        return None

    registered = (reference.get("feature_sets") or {}).get(feature_version)
    if registered is None:
        return None

    actual = [str(name) for name in feature_columns]
    expected = [str(name) for name in registered]

    if actual == expected:
        return None

    missing = [name for name in expected if name not in actual]
    unexpected = [name for name in actual if name not in expected]
    same_members = not missing and not unexpected

    if same_members:
        reason = "order_mismatch"
        detail = (f"i njejti set features por ne renditje tjeter "
                  f"({sum(1 for a, b in zip(actual, expected) if a != b)} pozicione "
                  f"ndryshojne)")
    else:
        reason = "member_mismatch"
        detail = (f"{len(missing)} features mungojne, {len(unexpected)} te tepert "
                  f"(artefakti ka {len(actual)}, '{feature_version}' ka {len(expected)})")

    return {
        "reason": reason,
        "declared_feature_version": feature_version,
        "declared_n_features": len(expected),
        "actual_n_features": len(actual),
        "missing_from_artifact": missing[:10],
        "unexpected_in_artifact": unexpected[:10],
        "resolved_feature_version": resolve_feature_version(actual, reference),
        "message": (f"Artefakti NUK perputhet me feature set-in '{feature_version}': "
                    f"{detail}. Modeli dhe feature schema jane cift i versionuar - "
                    f"mos e perdor modelin me nje feature set tjeter."),
    }


def resolve_feature_version(feature_columns, reference):
    if not reference:
        return None
    wanted = list(feature_columns)
    for version, columns in reference.get("feature_sets", {}).items():
        if list(columns) == wanted:
            return version
    for version, columns in reference.get("feature_sets", {}).items():
        if set(columns) == set(wanted):
            return version
    return None


class FeatureValidator:
    def __init__(self, feature_columns, reference=None, feature_version=None,
                 policy=STRICT_POLICY):
        self.feature_columns = [str(column) for column in feature_columns]
        self.expected = set(self.feature_columns)
        self.reference = reference
        self.policy = policy
        self.feature_version = (
            feature_version
            or resolve_feature_version(self.feature_columns, reference)
            or f"unregistered-{len(self.feature_columns)}-features"
        )
        self.reference_features = (reference or {}).get("features", {})

    def _range_check(self, feature, value, result):
        stats = self.reference_features.get(feature)
        if not stats:
            return
        low = stats.get("p01")
        high = stats.get("p99")
        if low is None or high is None or low == high:
            return
        if low <= value <= high:
            return
        result.out_of_range_features.append({
            "feature": feature,
            "value": value,
            "training_p01": low,
            "training_p99": high,
        })

    def validate(self, raw_features):
        result = FeatureValidationResult(self.feature_version, self.policy.name)

        pool = {}
        failures = {}
        for key, raw in (raw_features or {}).items():
            number, reason = _parse(raw)
            if reason is None:
                pool[key] = number
            else:
                failures[key] = reason

        result.unexpected_features = [
            key for key in (raw_features or {}) if key not in self.expected
        ]

        resolved = {}
        for feature in self.feature_columns:
            if feature in pool:
                resolved[feature] = pool[feature]

        for feature in self.feature_columns:
            if feature in resolved:
                continue

            reason = failures.get(feature, REASON_MISSING)

            if self.policy.allow_derivation and feature in DERIVATIONS:
                rule = DERIVATIONS[feature]
                if all(name in pool for name in rule["inputs"]):
                    derived = rule["function"](pool)
                    if derived is not None and math.isfinite(derived):
                        resolved[feature] = derived
                        result.derived_features.append({
                            "feature": feature,
                            "reason": reason,
                            "inputs": list(rule["inputs"]),
                            "verified_exact_rate": rule["exact_rate"],
                        })
                        continue

            if self.policy.allow_const_zero_fill and feature in CONST_ZERO_IN_TRAINING:
                resolved[feature] = 0.0
                result.zero_filled_features.append(feature)
                continue

            if reason == REASON_MISSING:
                result.missing_features.append(feature)
            else:
                result.invalid_features.append({"feature": feature, "reason": reason})

        if result.missing_features and self.policy.reject_on_missing:
            result.valid = False
        if result.invalid_features and self.policy.reject_on_invalid:
            result.valid = False

        for feature in result.missing_features:
            if feature in DERIVATIONS:
                missing_inputs = [
                    name for name in DERIVATIONS[feature]["inputs"] if name not in pool
                ]
                result.warnings.append(
                    f"{feature}: absent and not derivable, inputs also unavailable: "
                    f"{', '.join(missing_inputs)}"
                )
            else:
                result.warnings.append(
                    f"{feature}: absent and no verified derivation rule exists"
                )

        for entry in result.invalid_features:
            result.warnings.append(f"{entry['feature']}: value rejected ({entry['reason']})")

        if not result.valid:
            return result

        for feature in self.feature_columns:
            if feature not in resolved:
                resolved[feature] = 0.0
                if feature not in result.zero_filled_features:
                    result.zero_filled_features.append(feature)

        if self.policy.range_check:
            for feature in self.feature_columns:
                self._range_check(feature, resolved[feature], result)
            if result.out_of_range_features:
                result.warnings.append(
                    f"{len(result.out_of_range_features)} feature(s) outside the training "
                    f"p01-p99 range; prediction still produced"
                )

        result.vector = [resolved[feature] for feature in self.feature_columns]
        return result

    def validate_or_raise(self, raw_features):
        result = self.validate(raw_features)
        if not result.valid:
            raise FeatureValidationError(result)
        return result
