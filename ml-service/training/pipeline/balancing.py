import numpy as np

SMOTE_MIN_CLASS_ROWS = 2
DEFAULT_SMOTE_K_NEIGHBORS = 5

METHOD_UNCHANGED = "unchanged"
METHOD_UNDERSAMPLED = "undersampled"
METHOD_SMOTE = "smote"
METHOD_REPLICATED = "replicated"


class BalancingError(RuntimeError):
    pass


def class_counts(labels):
    names, counts = np.unique(labels, return_counts=True)
    return {str(name): int(count) for name, count in zip(names, counts)}


def plan_targets(counts, benign_label="BENIGN", benign_cap=None, rare_class_min=None):
    plan = {}
    for name, available in sorted(counts.items()):
        target = available
        method = METHOD_UNCHANGED

        if name == benign_label and benign_cap is not None and available > benign_cap:
            target = int(benign_cap)
            method = METHOD_UNDERSAMPLED
        elif name != benign_label and rare_class_min is not None and available < rare_class_min:
            target = int(rare_class_min)
            method = METHOD_SMOTE

        plan[name] = {"available": int(available), "target": int(target), "method": method}
    return plan


def planned_total(plan):
    return sum(entry["target"] for entry in plan.values())


def resolve_k_neighbors(plan, requested):
    oversampled = [entry["available"] for entry in plan.values()
                   if entry["method"] == METHOD_SMOTE]
    if not oversampled:
        return None

    smallest = min(oversampled)
    if smallest < SMOTE_MIN_CLASS_ROWS:
        return None

    return max(1, min(int(requested), smallest - 1))


def _undersample(labels, indices, plan, rng):
    kept = []
    for name, entry in plan.items():
        positions = indices[labels[indices] == name]
        if entry["method"] == METHOD_UNDERSAMPLED and len(positions) > entry["target"]:
            positions = rng.choice(positions, size=entry["target"], replace=False)
            positions = np.sort(positions)
        kept.append(positions)

    if not kept:
        return indices[:0]
    return np.sort(np.concatenate(kept))


def _replicate(features, labels, plan, rng):
    extra_features = []
    extra_labels = []
    replicated = []

    for name, entry in plan.items():
        if entry["method"] != METHOD_SMOTE:
            continue
        if entry["available"] >= SMOTE_MIN_CLASS_ROWS:
            continue

        deficit = entry["target"] - entry["available"]
        if deficit <= 0:
            continue

        positions = np.flatnonzero(labels == name)
        picks = rng.choice(positions, size=deficit, replace=True)
        extra_features.append(features[picks])
        extra_labels.append(np.array([name] * deficit, dtype=object))
        entry["method"] = METHOD_REPLICATED
        replicated.append(name)

    if not extra_features:
        return features, labels, replicated

    features = np.vstack([features] + extra_features)
    labels = np.concatenate([labels] + extra_labels)
    return features, labels, replicated


def _smote_strategy(plan, counts):
    strategy = {}
    for name, entry in plan.items():
        if entry["method"] != METHOD_SMOTE:
            continue
        if counts.get(name, 0) >= entry["target"]:
            continue
        strategy[name] = entry["target"]
    return strategy


def balance_training_set(features, labels, train_idx, config_balancing, seed):
    benign_label = config_balancing.get("benign_label", "BENIGN")
    benign_cap = config_balancing.get("benign_cap")
    rare_class_min = config_balancing.get("rare_class_min")
    oversampler = config_balancing.get("oversampler", "smote")
    requested_k = config_balancing.get("smote_k_neighbors", DEFAULT_SMOTE_K_NEIGHBORS)

    train_idx = np.asarray(train_idx)
    before = class_counts(labels[train_idx])

    if not config_balancing.get("enabled", True):
        report = {
            "enabled": False,
            "strategy": "none",
            "seed": int(seed),
            "rows_before": int(len(train_idx)),
            "rows_after": int(len(train_idx)),
            "class_counts_before": before,
            "class_counts_after": before,
            "plan": {},
            "smote_k_neighbors": None,
            "replicated_classes": [],
            "synthetic_rows": 0,
        }
        return features[train_idx], labels[train_idx], report

    plan = plan_targets(before, benign_label, benign_cap, rare_class_min)
    if oversampler == "none":
        for entry in plan.values():
            if entry["method"] == METHOD_SMOTE:
                entry["target"] = entry["available"]
                entry["method"] = METHOD_UNCHANGED

    rng = np.random.default_rng(seed)

    kept = _undersample(labels, train_idx, plan, rng)
    X = features[kept]
    y = labels[kept]

    k_neighbors = None
    replicated = []
    if oversampler == "smote":
        X, y, replicated = _replicate(X, y, plan, rng)
        strategy = _smote_strategy(plan, class_counts(y))
        if strategy:
            k_neighbors = resolve_k_neighbors(plan, requested_k)
            if k_neighbors is None:
                raise BalancingError(
                    "SMOTE kerkon te pakten 2 rreshta per klase; disa klasa te synuara "
                    "kane vetem 1. Ul rare_class_min ose perdor oversampler: none.")
            from imblearn.over_sampling import SMOTE

            sampler = SMOTE(sampling_strategy=strategy, k_neighbors=k_neighbors,
                            random_state=seed)
            X, y = sampler.fit_resample(X, y)

    order = rng.permutation(len(y))
    X = X[order]
    y = y[order]

    after = class_counts(y)
    synthetic = max(0, len(y) - len(kept))

    report = {
        "enabled": True,
        "strategy": _strategy_name(benign_cap, rare_class_min, oversampler),
        "seed": int(seed),
        "benign_label": benign_label,
        "benign_cap": int(benign_cap) if benign_cap is not None else None,
        "rare_class_min": int(rare_class_min) if rare_class_min is not None else None,
        "oversampler": oversampler,
        "smote_k_neighbors": k_neighbors,
        "rows_before": int(len(train_idx)),
        "rows_after": int(len(y)),
        "rows_after_undersampling": int(len(kept)),
        "synthetic_rows": int(synthetic),
        "replicated_classes": replicated,
        "class_counts_before": before,
        "class_counts_after": after,
        "plan": plan,
        "planned_total": int(planned_total(plan)),
    }

    return X, y, report


def _strategy_name(benign_cap, rare_class_min, oversampler):
    parts = []
    if benign_cap is not None:
        parts.append(f"undersample_benign_{benign_cap // 1000}k")
    if rare_class_min is not None and oversampler != "none":
        parts.append(f"oversample_rare_{rare_class_min // 1000}k"
                     if rare_class_min >= 1000 else f"oversample_rare_{rare_class_min}")
    return "_".join(parts) if parts else "none"
