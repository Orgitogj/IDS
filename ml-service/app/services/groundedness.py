import re

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

FINDING_IP_ADDRESS = "ip_address_not_in_evidence"
FINDING_PAYLOAD_CLAIM = "payload_or_packet_content_claim"
FINDING_PORT_NOT_IN_EVIDENCE = "port_not_in_evidence"
FINDING_PROTOCOL_NOT_IN_EVIDENCE = "protocol_not_in_evidence"

NUMERIC_TOLERANCE = 1e-6

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(r"\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b", re.IGNORECASE)

PORT_MENTION = re.compile(
    r"\b(?:port(?:a|at|it|in|es)?|porti)\s*(?:nr\.?|numer|numri)?\s*[:#]?\s*(\d{1,5})\b",
    re.IGNORECASE)

PAYLOAD_TERMS = [
    r"payload",
    r"permbajtj\w*\s+e\s+paketa\w*",
    r"përmbajtj\w*\s+e\s+paketa\w*",
    r"permbajtjen\s+e\s+trafikut",
    r"packet\s+capture",
    r"deep\s+packet",
    r"kodi\s+i\s+shfrytezimit",
    r"exploit\s+code",
    r"shell\s?code",
]

PAYLOAD = [re.compile(term, re.IGNORECASE) for term in PAYLOAD_TERMS]

PROTOCOL_NAMES = [
    "HTTP", "HTTPS", "DNS", "SMTP", "IMAP", "POP3", "TELNET", "RDP", "SMB", "NTP",
    "SNMP", "LDAP", "TLS", "SSL", "ICMP", "ARP", "DHCP", "SIP", "MQTT",
]

PROTOCOL_PATTERNS = {
    name: re.compile(rf"\b{name}\b", re.IGNORECASE) for name in PROTOCOL_NAMES
}

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _numeric_forms(value):
    number = float(value)
    forms = {number}
    for digits in (0, 1, 2, 3):
        forms.add(round(number, digits))
    if number.is_integer():
        forms.add(float(int(number)))
    return forms


def _parse_number(text):
    cleaned = text.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


class Evidence:

    def __init__(self, predicted_label=None, confidence=None, shap_features=None,
                 anomaly_features=None, anomaly_score=None, extra_terms=None):
        self.predicted_label = predicted_label
        self.confidence = confidence
        self.shap_features = list(shap_features or [])
        self.anomaly_features = list(anomaly_features or [])
        self.anomaly_score = anomaly_score
        self.extra_terms = list(extra_terms or [])

        self.feature_names = [str(entry["feature"]) for entry in
                              self.shap_features + self.anomaly_features]
        self.numbers = self._collect_numbers()
        self.text = self._collect_text()

    def _collect_numbers(self):
        numbers = set()
        for entry in self.shap_features:
            numbers |= _numeric_forms(entry["value"])
            numbers |= _numeric_forms(entry["shap_contribution"])
        for entry in self.anomaly_features:
            numbers |= _numeric_forms(entry["value"])
            numbers |= _numeric_forms(entry["baseline_value"])
            numbers |= _numeric_forms(entry["anomaly_contribution"])
        if self.confidence is not None:
            numbers |= _numeric_forms(self.confidence)
            numbers |= _numeric_forms(float(self.confidence) * 100.0)
        if self.anomaly_score is not None:
            numbers |= _numeric_forms(self.anomaly_score)
        return numbers

    def _collect_text(self):
        parts = list(self.feature_names) + list(self.extra_terms)
        if self.predicted_label:
            parts.append(str(self.predicted_label))
        return " ".join(parts).lower()

    def mentions_number(self, value):
        if value is None:
            return False
        for candidate in self.numbers:
            if abs(candidate - value) <= NUMERIC_TOLERANCE:
                return True
        return False

    def mentions_term(self, term):
        return term.lower() in self.text


def _finding(kind, severity, matched, detail):
    return {"kind": kind, "severity": severity, "matched": matched, "detail": detail}


def check(explanation_text, evidence):
    text = explanation_text or ""
    findings = []

    for match in IPV4.finditer(text):
        findings.append(_finding(
            FINDING_IP_ADDRESS, SEVERITY_HIGH, match.group(0),
            "The model was given no IP address; the feature vector contains none."))

    for match in IPV6.finditer(text):
        if IPV4.search(match.group(0)):
            continue
        findings.append(_finding(
            FINDING_IP_ADDRESS, SEVERITY_HIGH, match.group(0),
            "The model was given no IP address; the feature vector contains none."))

    for pattern in PAYLOAD:
        for match in pattern.finditer(text):
            findings.append(_finding(
                FINDING_PAYLOAD_CLAIM, SEVERITY_HIGH, match.group(0),
                "The model receives aggregate flow statistics only, never packet "
                "contents."))

    for match in PORT_MENTION.finditer(text):
        port = _parse_number(match.group(1))
        if evidence.mentions_number(port):
            continue
        findings.append(_finding(
            FINDING_PORT_NOT_IN_EVIDENCE, SEVERITY_MEDIUM, match.group(0),
            f"Port {match.group(1)} appears in no feature value supplied to the model."))

    for name, pattern in PROTOCOL_PATTERNS.items():
        if evidence.mentions_term(name):
            continue
        for match in pattern.finditer(text):
            findings.append(_finding(
                FINDING_PROTOCOL_NOT_IN_EVIDENCE, SEVERITY_MEDIUM, match.group(0),
                f"{name} is named in no feature supplied to the model; the feature set "
                "carries no protocol identity."))
            break

    return {
        "grounded": not findings,
        "finding_count": len(findings),
        "high_severity_count": sum(1 for entry in findings
                                   if entry["severity"] == SEVERITY_HIGH),
        "findings": findings,
        "method": "deterministic_heuristic_v1",
        "caveat": "Heuristic only. It detects entities the model could not possibly have "
                  "been given - IP addresses, packet contents, ports and protocols absent "
                  "from the evidence. It does NOT verify that the explanation is "
                  "semantically correct, and a clean result is not evidence of "
                  "correctness.",
    }


def evidence_from_prediction(prediction):
    return Evidence(
        predicted_label=prediction.get("prediction") or prediction.get("predicted_label"),
        confidence=prediction.get("confidence"),
        shap_features=prediction.get("top_shap_features"),
        anomaly_features=prediction.get("top_anomaly_features"),
        anomaly_score=prediction.get("anomaly_score"),
    )
