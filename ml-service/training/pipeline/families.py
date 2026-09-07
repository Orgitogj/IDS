TAXONOMY_VERSION = "cicids2017-families-v1"

BENIGN = "BENIGN"

FAMILY_BRUTE_FORCE = "Brute Force"
FAMILY_DOS = "DoS"
FAMILY_DDOS = "DDoS"
FAMILY_WEB_ATTACK = "Web Attack"
FAMILY_INFILTRATION = "Infiltration"
FAMILY_BOT = "Bot"
FAMILY_PORTSCAN = "PortScan"
FAMILY_HEARTBLEED = "Heartbleed"

FAMILIES = {
    FAMILY_BRUTE_FORCE: {
        "labels": ["FTP-Patator", "SSH-Patator"],
        "scenario": "Tuesday: credential brute force driven by the Patator tool against "
                    "FTP and SSH.",
        "rationale": "Both labels are the same tool and the same attack mechanism against "
                     "different services. Holding out only one would leave the other in "
                     "training and the family would not be unseen.",
    },
    FAMILY_DOS: {
        "labels": ["DoS Hulk", "DoS GoldenEye", "DoS slowloris", "DoS Slowhttptest"],
        "scenario": "Wednesday morning: single-source application-layer denial of service.",
        "rationale": "Four tools producing the same class of resource-exhaustion "
                     "behaviour in one contiguous window. Removing one at a time leaves "
                     "near-identical traffic in training.",
    },
    FAMILY_DDOS: {
        "labels": ["DDoS"],
        "scenario": "Friday afternoon: distributed denial of service (LOIC).",
        "rationale": "Kept separate from DoS because CICIDS2017 generated it on a "
                     "different day with a distributed source model. See the note on "
                     "RELATED_FAMILIES - the two are mechanically adjacent and the "
                     "DoS/DDoS folds are not independent of each other.",
    },
    FAMILY_WEB_ATTACK: {
        "labels": ["Web Attack - Brute Force", "Web Attack - XSS",
                   "Web Attack - Sql Injection"],
        "scenario": "Thursday morning: web application attacks against DVWA.",
        "rationale": "Three sub-labels of one scenario against one target in one window.",
    },
    FAMILY_INFILTRATION: {
        "labels": ["Infiltration"],
        "scenario": "Thursday afternoon: infiltration from inside the network.",
        "rationale": "Single label, single scenario.",
    },
    FAMILY_BOT: {
        "labels": ["Bot"],
        "scenario": "Friday morning: botnet command-and-control activity (Ares).",
        "rationale": "Single label, single scenario.",
    },
    FAMILY_PORTSCAN: {
        "labels": ["PortScan"],
        "scenario": "Friday afternoon: port scanning (nmap).",
        "rationale": "Single label, single scenario.",
    },
    FAMILY_HEARTBLEED: {
        "labels": ["Heartbleed"],
        "scenario": "Wednesday afternoon: Heartbleed exploitation.",
        "rationale": "Single label. Kept out of the DoS family because it is an "
                     "information-disclosure exploit, not resource exhaustion, despite "
                     "sharing the Wednesday capture.",
    },
}

RELATED_FAMILIES = [
    {
        "families": [FAMILY_DOS, FAMILY_DDOS],
        "note": ("DoS and DDoS are treated as separate families because CICIDS2017 "
                 "generated them as separate scenarios on separate days with different "
                 "source models. They remain mechanically adjacent: when DDoS is held "
                 "out, four DoS labels stay in training, and vice versa. Detection of a "
                 "held-out DDoS family is therefore NOT evidence of generalisation to an "
                 "unrelated attack type."),
    },
    {
        "families": [FAMILY_BRUTE_FORCE, FAMILY_WEB_ATTACK],
        "note": ("Web Attack - Brute Force is a web-form credential attack while the "
                 "Brute Force family is FTP/SSH credential attack. They are separate "
                 "families here because they target different protocols in different "
                 "scenarios, but they share the notion of repeated authentication "
                 "attempts."),
    },
]

LABEL_TO_FAMILY = {label: family
                   for family, entry in FAMILIES.items()
                   for label in entry["labels"]}


class TaxonomyError(ValueError):
    pass


def family_of(label):
    if label == BENIGN:
        return BENIGN
    return LABEL_TO_FAMILY.get(label)


def member_labels(family):
    if family not in FAMILIES:
        raise TaxonomyError(f"Familje e panjohur: {family}")
    return list(FAMILIES[family]["labels"])


def all_families():
    return sorted(FAMILIES)


def validate_against(labels):
    observed = set(str(name) for name in labels)
    observed.discard(BENIGN)

    mapped = set(LABEL_TO_FAMILY)
    unmapped = sorted(observed - mapped)
    unknown = sorted(mapped - observed)

    if unmapped:
        raise TaxonomyError(
            f"Etiketa pa familje ne taksonomi: {unmapped}. Cdo etikete sulmi duhet t'i "
            "perkase nje familjeje; perndryshe nje fold LOFO do te linte trafik te lidhur "
            "ne trajnim.")

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "labels_observed": sorted(observed),
        "labels_mapped": sorted(mapped),
        "labels_in_taxonomy_but_absent_from_data": unknown,
        "families": all_families(),
        "complete": True,
    }


def describe(labels, train_idx=None, test_idx=None):
    import numpy as np

    labels = np.asarray(labels, dtype=object)
    entries = {}

    for family in all_families():
        members = member_labels(family)
        mask = np.isin(labels, members)

        entry = {
            "family": family,
            "member_labels": members,
            "n_member_labels": len(members),
            "scenario": FAMILIES[family]["scenario"],
            "rationale": FAMILIES[family]["rationale"],
            "total_support": int(mask.sum()),
            "per_label_total": {label: int((labels == label).sum())
                                for label in members},
        }

        if train_idx is not None:
            train_mask = np.isin(labels[train_idx], members)
            entry["train_support"] = int(train_mask.sum())
            entry["per_label_train"] = {
                label: int((labels[train_idx] == label).sum()) for label in members}

        if test_idx is not None:
            test_mask = np.isin(labels[test_idx], members)
            entry["test_support"] = int(test_mask.sum())
            entry["per_label_test"] = {
                label: int((labels[test_idx] == label).sum()) for label in members}

        entries[family] = entry

    return entries


SUPPORT_HIGH = "high"
SUPPORT_MODERATE = "moderate"
SUPPORT_LOW = "low_exploratory"

HIGH_SUPPORT_MIN = 1000
MODERATE_SUPPORT_MIN = 100


def support_tier(test_support):
    if test_support >= HIGH_SUPPORT_MIN:
        return SUPPORT_HIGH
    if test_support >= MODERATE_SUPPORT_MIN:
        return SUPPORT_MODERATE
    return SUPPORT_LOW
