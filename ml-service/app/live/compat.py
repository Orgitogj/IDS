from app.live import protocol

COMPAT_PROTOCOL = "lab-feature-compat-v1"
TARGET_FEATURE_CONTRACT = protocol.FROZEN_PRIMARY_MODEL["feature_version"]
SOURCE_FEATURE_SEMANTICS = "cicflowmeter-0.5.0"
SECONDS_TO_MICROSECONDS = 1_000_000

CONFIRMED_SECONDS_FEATURES = [
    "Flow Duration",
    "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max",
    "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max",
    "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
]

LIKELY_SECONDS_FEATURES_ALL_ZERO_IN_LAB = [
    "Flow IAT Min", "Fwd IAT Min",
    "Active Mean", "Active Std", "Active Max", "Active Min",
    "Idle Mean", "Idle Std", "Idle Max", "Idle Min",
]

RATE_FEATURES_NOT_CONVERTED = [
    "Flow Bytes/s", "Flow Packets/s", "Fwd Packets/s", "Bwd Packets/s",
]

APPLIED_MARKER = "_lab_feature_compat_applied"


class CompatError(RuntimeError):
    pass


def _check_finite(value, feature):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CompatError(f"{feature}: jo-numerike gjate harmonizimit") from error
    if number != number or number in (float("inf"), float("-inf")):
        raise CompatError(f"{feature}: vlere jo-e-fundme gjate harmonizimit")
    return number


def harmonize_vector(feature_columns, vector, feature_schema=TARGET_FEATURE_CONTRACT):
    columns = [str(name) for name in feature_columns]

    if feature_schema != TARGET_FEATURE_CONTRACT:
        raise CompatError(
            f"schema '{feature_schema}' nuk eshte kontrata e synuar "
            f"'{TARGET_FEATURE_CONTRACT}'")
    if len(columns) != protocol.FROZEN_PRIMARY_MODEL["n_features"]:
        raise CompatError(
            f"pritej {protocol.FROZEN_PRIMARY_MODEL['n_features']} features, u gjeten "
            f"{len(columns)}")
    if len(vector) != len(columns):
        raise CompatError("gjatesia e vektorit nuk perputhet me feature_columns")

    missing = [name for name in CONFIRMED_SECONDS_FEATURES if name not in columns]
    if missing:
        raise CompatError(f"features te konfirmuara mungojne nga schema: {missing}")

    positions = {name: i for i, name in enumerate(columns)}
    new_vector = [float(v) for v in vector]
    converted = []
    for name in CONFIRMED_SECONDS_FEATURES:
        j = positions[name]
        value = _check_finite(vector[j], name)
        new_vector[j] = value * SECONDS_TO_MICROSECONDS
        converted.append(name)

    metadata = {
        "compatibility_protocol": COMPAT_PROTOCOL,
        "source_feature_semantics": SOURCE_FEATURE_SEMANTICS,
        "target_feature_contract": TARGET_FEATURE_CONTRACT,
        "compatibility_applied": True,
        "conversion": "seconds_to_microseconds",
        "conversion_factor": SECONDS_TO_MICROSECONDS,
        "converted_features": converted,
        "converted_feature_count": len(converted),
        "rate_features_left_unchanged": list(RATE_FEATURES_NOT_CONVERTED),
    }
    return new_vector, metadata


def harmonize_record(record):
    if not isinstance(record, dict):
        raise CompatError("harmonize_record kerkon nje dict")
    if record.get(APPLIED_MARKER):
        raise CompatError(
            "harmonizimi tashme eshte aplikuar; aplikim i dyfishte i ndaluar")
    stamped = dict(record)
    stamped[APPLIED_MARKER] = COMPAT_PROTOCOL
    return stamped


def is_applied(record):
    return bool(isinstance(record, dict) and record.get(APPLIED_MARKER))
