import math


def _get(values, name):
    value = values.get(name)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _all(values, names):
    resolved = []
    for name in names:
        number = _get(values, name)
        if number is None:
            return None
        resolved.append(number)
    return resolved


def _per_second(count, duration_us):
    if duration_us == 0:
        return None
    return count / (duration_us / 1e6)


def _avg_fwd_segment_size(values):
    resolved = _all(values, ("Fwd Packet Length Mean",))
    return resolved[0] if resolved else None


def _avg_bwd_segment_size(values):
    resolved = _all(values, ("Bwd Packet Length Mean",))
    return resolved[0] if resolved else None


def _subflow_fwd_packets(values):
    resolved = _all(values, ("Total Fwd Packets",))
    return resolved[0] if resolved else None


def _subflow_bwd_packets(values):
    resolved = _all(values, ("Total Backward Packets",))
    return resolved[0] if resolved else None


def _subflow_fwd_bytes(values):
    resolved = _all(values, ("Total Length of Fwd Packets",))
    return resolved[0] if resolved else None


def _subflow_bwd_bytes(values):
    resolved = _all(values, ("Total Length of Bwd Packets",))
    return resolved[0] if resolved else None


def _down_up_ratio(values):
    resolved = _all(values, ("Total Backward Packets", "Total Fwd Packets"))
    if not resolved:
        return None
    backward, forward = resolved
    if forward == 0:
        return None
    return math.floor(backward / forward)


def _max_packet_length(values):
    resolved = _all(values, ("Fwd Packet Length Max", "Bwd Packet Length Max"))
    if not resolved:
        return None
    return max(resolved)


def _min_packet_length(values):
    resolved = _all(values, ("Fwd Packet Length Min", "Bwd Packet Length Min",
                             "Total Backward Packets"))
    if not resolved:
        return None
    forward_min, backward_min, backward_packets = resolved
    if backward_packets == 0:
        return forward_min
    return min(forward_min, backward_min)


def _flow_packets_per_second(values):
    resolved = _all(values, ("Total Fwd Packets", "Total Backward Packets", "Flow Duration"))
    if not resolved:
        return None
    forward, backward, duration = resolved
    return _per_second(forward + backward, duration)


def _fwd_packets_per_second(values):
    resolved = _all(values, ("Total Fwd Packets", "Flow Duration"))
    if not resolved:
        return None
    return _per_second(resolved[0], resolved[1])


def _bwd_packets_per_second(values):
    resolved = _all(values, ("Total Backward Packets", "Flow Duration"))
    if not resolved:
        return None
    return _per_second(resolved[0], resolved[1])


def _flow_bytes_per_second(values):
    resolved = _all(values, ("Total Length of Fwd Packets", "Total Length of Bwd Packets",
                             "Flow Duration"))
    if not resolved:
        return None
    forward, backward, duration = resolved
    return _per_second(forward + backward, duration)


def _packet_length_variance(values):
    resolved = _all(values, ("Packet Length Std",))
    if not resolved:
        return None
    return resolved[0] ** 2


def _flow_iat_mean(values):
    resolved = _all(values, ("Flow Duration", "Total Fwd Packets", "Total Backward Packets"))
    if not resolved:
        return None
    duration, forward, backward = resolved
    packets = forward + backward
    if packets <= 1:
        return None
    return duration / (packets - 1)


DERIVATIONS = {
    "Avg Fwd Segment Size": {
        "inputs": ("Fwd Packet Length Mean",),
        "function": _avg_fwd_segment_size,
        "exact_rate": 1.0,
        "note": "Identical column in CICIDS2017.",
    },
    "Avg Bwd Segment Size": {
        "inputs": ("Bwd Packet Length Mean",),
        "function": _avg_bwd_segment_size,
        "exact_rate": 1.0,
        "note": "Identical column in CICIDS2017.",
    },
    "Subflow Fwd Packets": {
        "inputs": ("Total Fwd Packets",),
        "function": _subflow_fwd_packets,
        "exact_rate": 1.0,
        "note": "CICIDS2017 flows carry a single subflow.",
    },
    "Subflow Bwd Packets": {
        "inputs": ("Total Backward Packets",),
        "function": _subflow_bwd_packets,
        "exact_rate": 1.0,
        "note": "CICIDS2017 flows carry a single subflow.",
    },
    "Subflow Fwd Bytes": {
        "inputs": ("Total Length of Fwd Packets",),
        "function": _subflow_fwd_bytes,
        "exact_rate": 1.0,
        "note": "CICIDS2017 flows carry a single subflow.",
    },
    "Subflow Bwd Bytes": {
        "inputs": ("Total Length of Bwd Packets",),
        "function": _subflow_bwd_bytes,
        "exact_rate": 1.0,
        "note": "CICIDS2017 flows carry a single subflow.",
    },
    "Down/Up Ratio": {
        "inputs": ("Total Backward Packets", "Total Fwd Packets"),
        "function": _down_up_ratio,
        "exact_rate": 1.0,
        "note": "Integer-floored ratio.",
    },
    "Max Packet Length": {
        "inputs": ("Fwd Packet Length Max", "Bwd Packet Length Max"),
        "function": _max_packet_length,
        "exact_rate": 1.0,
        "note": "Maximum of the two directional maxima.",
    },
    "Min Packet Length": {
        "inputs": ("Fwd Packet Length Min", "Bwd Packet Length Min", "Total Backward Packets"),
        "function": _min_packet_length,
        "exact_rate": 1.0,
        "note": "Backward minimum is recorded as 0 when no backward packet exists and must be ignored.",
    },
    "Flow Packets/s": {
        "inputs": ("Total Fwd Packets", "Total Backward Packets", "Flow Duration"),
        "function": _flow_packets_per_second,
        "exact_rate": 1.0,
        "note": "Flow Duration is in microseconds.",
    },
    "Fwd Packets/s": {
        "inputs": ("Total Fwd Packets", "Flow Duration"),
        "function": _fwd_packets_per_second,
        "exact_rate": 0.9999,
        "note": "Flow Duration is in microseconds.",
    },
    "Bwd Packets/s": {
        "inputs": ("Total Backward Packets", "Flow Duration"),
        "function": _bwd_packets_per_second,
        "exact_rate": 0.9999,
        "note": "Flow Duration is in microseconds.",
    },
    "Packet Length Variance": {
        "inputs": ("Packet Length Std",),
        "function": _packet_length_variance,
        "exact_rate": 0.9932,
        "note": "Square of the standard deviation; rounding in the source data costs the remainder.",
    },
    "Flow Bytes/s": {
        "inputs": ("Total Length of Fwd Packets", "Total Length of Bwd Packets", "Flow Duration"),
        "function": _flow_bytes_per_second,
        "exact_rate": 0.9919,
        "note": "Flow Duration is in microseconds.",
    },
    "Flow IAT Mean": {
        "inputs": ("Flow Duration", "Total Fwd Packets", "Total Backward Packets"),
        "function": _flow_iat_mean,
        "exact_rate": 0.9852,
        "note": "Exact only when the flow has no idle-period splitting.",
    },
}

NOT_DERIVABLE = {
    "Average Packet Size": "Implied denominator is fractional against the packet counts, so the "
                           "CICIDS2017 definition uses a byte total that the other columns do not "
                           "expose. Measured agreement with totalBytes/totalPackets is only 40.9%.",
}

MIN_TRUSTED_EXACT_RATE = 0.98


def derivable_features():
    return tuple(DERIVATIONS)


def can_derive(feature, available_features):
    rule = DERIVATIONS.get(feature)
    if rule is None:
        return False
    return all(name in available_features for name in rule["inputs"])


def derive(feature, values):
    rule = DERIVATIONS.get(feature)
    if rule is None:
        return None
    return rule["function"](values)
