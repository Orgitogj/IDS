import json
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_THRESHOLDS_PATH = _ML_SERVICE_ROOT / "reports" / "drift_thresholds.json"

STATUS_NORMAL = "NORMAL"
STATUS_WARNING = "WARNING"
STATUS_CRITICAL = "CRITICAL"

INVALID_RATE_WARNING = 0.01
INVALID_RATE_CRITICAL = 0.05
MISSING_RATE_CRITICAL = 0.01
DRIFTED_FRACTION_CRITICAL = 0.20


def ks_against_reference(sample, quantiles, percentiles):
    values = np.asarray(sample, dtype="float64")
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.0

    low = float(quantiles[0])
    high = float(quantiles[-1])
    if high <= low:
        return 0.0 if np.all(values == low) else 1.0

    values = np.sort(values)
    count = values.size
    reference_cdf = np.interp(values, quantiles, percentiles)
    upper = np.arange(1, count + 1, dtype="float64") / count
    lower = np.arange(0, count, dtype="float64") / count

    return float(max(np.max(upper - reference_cdf), np.max(reference_cdf - lower)))


def load_thresholds(path=None):
    thresholds_path = Path(path) if path else DEFAULT_THRESHOLDS_PATH
    if not thresholds_path.exists():
        return None
    with open(thresholds_path, encoding="utf-8") as handle:
        return json.load(handle)


class DriftMonitor:
    def __init__(self, feature_columns, reference, thresholds, window_size=1000,
                 feature_version=None):
        self.feature_columns = list(feature_columns)
        self.feature_version = feature_version
        self.reference = reference
        self.thresholds = thresholds
        self.window_size = window_size
        self.window = deque(maxlen=window_size)

        self.observed = 0
        self.accepted = 0
        self.rejected = 0
        self.rejection_reasons = Counter()
        self.missing_counts = Counter()
        self.invalid_counts = Counter()
        self.derived_counts = Counter()
        self.zero_filled_counts = Counter()
        self.out_of_range_counts = Counter()

        self._reference_quantiles = {}
        self._percentiles = None
        if reference is not None:
            self._percentiles = np.asarray(reference["quantile_grid"], dtype="float64")
            for name in self.feature_columns:
                stats = reference["features"].get(name)
                if stats is not None:
                    self._reference_quantiles[name] = np.asarray(stats["quantiles"],
                                                                  dtype="float64")

    def reset(self):
        self.window.clear()
        self.observed = 0
        self.accepted = 0
        self.rejected = 0
        self.rejection_reasons.clear()
        self.missing_counts.clear()
        self.invalid_counts.clear()
        self.derived_counts.clear()
        self.zero_filled_counts.clear()
        self.out_of_range_counts.clear()

    def record(self, validation):
        self.observed += 1

        for name in validation.missing_features:
            self.missing_counts[name] += 1
        for entry in validation.invalid_features:
            self.invalid_counts[entry["feature"]] += 1
            self.rejection_reasons[entry["reason"]] += 1
        for entry in validation.derived_features:
            self.derived_counts[entry["feature"]] += 1
        for name in validation.zero_filled_features:
            self.zero_filled_counts[name] += 1
        for entry in validation.out_of_range_features:
            self.out_of_range_counts[entry["feature"]] += 1

        if not validation.valid:
            self.rejected += 1
            if validation.missing_features:
                self.rejection_reasons["missing"] += len(validation.missing_features)
            return

        self.accepted += 1
        if validation.vector is not None:
            self.window.append(list(validation.vector))

    def _calibrated_window(self):
        if not self.thresholds:
            return None
        sizes = sorted(self.thresholds["windows"], key=lambda key: int(key))
        observed = len(self.window)
        best = min(sizes, key=lambda key: abs(int(key) - observed))
        return self.thresholds["windows"][best]

    def report(self):
        sample_size = len(self.window)
        invalid_rate = self.rejected / self.observed if self.observed else 0.0

        features = {}
        drifted = []
        calibration = self._calibrated_window()
        matrix = np.asarray(self.window, dtype="float64") if sample_size else None

        for position, name in enumerate(self.feature_columns):
            entry = {
                "missing_rate": self.missing_counts[name] / self.observed if self.observed else 0.0,
                "invalid_rate": self.invalid_counts[name] / self.observed if self.observed else 0.0,
                "derived_rate": self.derived_counts[name] / self.observed if self.observed else 0.0,
                "zero_filled_rate": (self.zero_filled_counts[name] / self.observed
                                     if self.observed else 0.0),
                "out_of_range_rate": (self.out_of_range_counts[name] / self.observed
                                      if self.observed else 0.0),
            }

            if matrix is not None:
                column = matrix[:, position]
                entry.update({
                    "mean": float(np.mean(column)),
                    "std": float(np.std(column, ddof=1)) if sample_size > 1 else 0.0,
                    "p25": float(np.quantile(column, 0.25)),
                    "p50": float(np.quantile(column, 0.50)),
                    "p75": float(np.quantile(column, 0.75)),
                })

                quantiles = self._reference_quantiles.get(name)
                if quantiles is not None and self._percentiles is not None:
                    statistic = ks_against_reference(column, quantiles, self._percentiles)
                    entry["ks_statistic"] = statistic

                    if calibration:
                        limit = calibration["feature_ks_thresholds"].get(name, {}).get("p95")
                        if limit is not None:
                            entry["ks_threshold"] = limit
                            entry["drifted"] = statistic > limit
                            if entry["drifted"]:
                                drifted.append(name)

            features[name] = entry

        drifted_fraction = len(drifted) / len(self.feature_columns) if self.feature_columns else 0.0
        status, reasons = self._status(invalid_rate, drifted_fraction, features, calibration)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": status,
            "reasons": reasons,
            "observed_flows": self.observed,
            "accepted_flows": self.accepted,
            "rejected_flows": self.rejected,
            "sample_size": sample_size,
            "invalid_rate": invalid_rate,
            "rejection_reasons": dict(self.rejection_reasons),
            "drifted_feature_count": len(drifted),
            "drifted_features": drifted,
            "drifted_fraction": drifted_fraction,
            "calibration_window": calibration["window_size"] if calibration else None,
            "feature_version": self.feature_version,
            "features": features,
        }

    def _status(self, invalid_rate, drifted_fraction, features, calibration):
        reasons = []
        status = STATUS_NORMAL

        if invalid_rate > INVALID_RATE_CRITICAL:
            reasons.append(f"invalid-vector rate {invalid_rate:.1%} above "
                           f"{INVALID_RATE_CRITICAL:.0%}")
            status = STATUS_CRITICAL
        elif invalid_rate > INVALID_RATE_WARNING:
            reasons.append(f"invalid-vector rate {invalid_rate:.1%} above "
                           f"{INVALID_RATE_WARNING:.0%}")
            status = STATUS_WARNING

        badly_missing = [name for name, entry in features.items()
                         if entry["missing_rate"] > MISSING_RATE_CRITICAL]
        if badly_missing:
            reasons.append(f"{len(badly_missing)} feature(s) missing in more than "
                           f"{MISSING_RATE_CRITICAL:.0%} of flows")
            status = STATUS_CRITICAL

        if calibration:
            null_fraction = calibration["drifted_fraction_thresholds"]["p99"]
            if drifted_fraction > DRIFTED_FRACTION_CRITICAL:
                reasons.append(f"{drifted_fraction:.1%} of features drifted, above the "
                               f"{DRIFTED_FRACTION_CRITICAL:.0%} policy limit")
                status = STATUS_CRITICAL
            elif drifted_fraction > null_fraction:
                reasons.append(f"{drifted_fraction:.1%} of features drifted, above the "
                               f"calibrated no-drift ceiling of {null_fraction:.1%}")
                if status == STATUS_NORMAL:
                    status = STATUS_WARNING

        if not reasons:
            reasons.append("within calibrated no-drift bounds")

        return status, reasons
