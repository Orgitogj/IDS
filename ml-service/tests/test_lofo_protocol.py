import json
from pathlib import Path

import numpy as np
import pytest

from training.pipeline import families, lofo

BENIGN = "BENIGN"


def make_labels(counts):
    labels = []
    for name, count in counts.items():
        labels.extend([name] * count)
    return np.array(labels, dtype=object)


@pytest.fixture
def labelled():
    return make_labels({
        BENIGN: 200,
        "DoS Hulk": 40, "DoS GoldenEye": 20, "DoS slowloris": 10, "DoS Slowhttptest": 10,
        "FTP-Patator": 15, "SSH-Patator": 15,
        "Web Attack - Brute Force": 8, "Web Attack - XSS": 6,
        "Web Attack - Sql Injection": 4,
        "DDoS": 30, "PortScan": 25, "Bot": 12, "Infiltration": 3, "Heartbleed": 2,
    })


class TestFamilyMapping:

    def test_every_cicids2017_attack_label_is_mapped(self, labelled):
        report = families.validate_against(labelled)

        assert report["complete"] is True
        assert report["labels_in_taxonomy_but_absent_from_data"] == []
        for label in labelled:
            if label != BENIGN:
                assert families.family_of(label) is not None

    def test_an_unmapped_label_is_refused(self):
        labels = make_labels({BENIGN: 5, "Brand New Attack": 3})

        with pytest.raises(families.TaxonomyError, match="pa familje"):
            families.validate_against(labels)

    def test_the_dos_family_holds_all_four_dos_labels(self):
        members = families.member_labels("DoS")

        assert sorted(members) == sorted(["DoS Hulk", "DoS GoldenEye", "DoS slowloris",
                                          "DoS Slowhttptest"])

    def test_the_web_attack_family_holds_all_three_sub_labels(self):
        members = families.member_labels("Web Attack")

        assert sorted(members) == sorted(["Web Attack - Brute Force", "Web Attack - XSS",
                                          "Web Attack - Sql Injection"])

    def test_the_brute_force_family_holds_both_patator_labels(self):
        assert sorted(families.member_labels("Brute Force")) == ["FTP-Patator",
                                                                 "SSH-Patator"]

    def test_dos_and_ddos_are_separate_but_flagged_as_related(self):
        assert "DDoS" not in families.member_labels("DoS")
        assert families.family_of("DDoS") == "DDoS"

        related = [entry for entry in families.RELATED_FAMILIES
                   if set(entry["families"]) == {"DoS", "DDoS"}]
        assert related and "NOT evidence" in related[0]["note"]

    def test_benign_is_not_an_attack_family(self):
        assert families.family_of(BENIGN) == BENIGN
        assert BENIGN not in families.all_families()

    def test_there_are_eight_families(self):
        assert len(families.all_families()) == 8

    def test_no_label_belongs_to_two_families(self):
        seen = []
        for family in families.all_families():
            seen.extend(families.member_labels(family))

        assert len(seen) == len(set(seen))

    def test_support_tiers_classify_rare_families_as_exploratory(self):
        assert families.support_tier(50_000) == families.SUPPORT_HIGH
        assert families.support_tier(435) == families.SUPPORT_MODERATE
        assert families.support_tier(7) == families.SUPPORT_LOW
        assert families.support_tier(2) == families.SUPPORT_LOW

    def test_rare_families_are_retained_in_the_taxonomy(self):
        assert "Heartbleed" in families.all_families()
        assert "Infiltration" in families.all_families()


class TestFamilyRemoval:

    def test_all_member_labels_leave_the_training_partition(self, labelled):
        train_idx = np.arange(0, 300)
        members = families.member_labels("DoS")

        kept, removed = lofo.remove_family_from_train(labelled, train_idx, members)

        assert removed > 0
        assert not np.isin(labelled[kept], members).any()

    def test_removal_only_touches_the_supplied_indices(self, labelled):
        train_idx = np.arange(0, 300)
        members = families.member_labels("DoS")

        kept, _ = lofo.remove_family_from_train(labelled, train_idx, members)

        assert set(kept.tolist()) <= set(train_idx.tolist())
        assert np.isin(labelled, members).sum() > 0

    def test_removal_is_deterministic(self, labelled):
        train_idx = np.arange(0, 300)
        members = families.member_labels("Web Attack")

        first, _ = lofo.remove_family_from_train(labelled, train_idx, members)
        second, _ = lofo.remove_family_from_train(labelled, train_idx, members)

        np.testing.assert_array_equal(first, second)

    def test_a_family_absent_from_train_removes_nothing(self, labelled):
        train_idx = np.arange(0, 200)
        kept, removed = lofo.remove_family_from_train(
            labelled, train_idx, families.member_labels("DDoS"))

        assert removed == 0
        np.testing.assert_array_equal(kept, train_idx)

    def test_balancing_output_containing_the_family_is_refused(self):
        balanced = make_labels({BENIGN: 10, "DoS Hulk": 2})

        with pytest.raises(lofo.LofoError, match="pas balancimit"):
            lofo.assert_absent_after_balancing(balanced, families.member_labels("DoS"))

    def test_clean_balancing_output_passes(self):
        balanced = make_labels({BENIGN: 10, "PortScan": 5})

        assert lofo.assert_absent_after_balancing(balanced,
                                                  families.member_labels("DoS"))

    def test_removal_then_balancing_is_the_required_order(self, labelled):
        from training.pipeline import balancing as balancing_module

        train_idx = np.arange(0, 300)
        members = families.member_labels("DoS")
        kept, _ = lofo.remove_family_from_train(labelled, train_idx, members)

        features = np.zeros((len(labelled), 3), dtype="float32")
        _, y_balanced, _ = balancing_module.balance_training_set(
            features, labelled, kept,
            {"enabled": True, "benign_label": BENIGN, "benign_cap": 100,
             "rare_class_min": 20, "oversampler": "smote", "smote_k_neighbors": 2}, 42)

        assert lofo.assert_absent_after_balancing(y_balanced, members)


class TestDetectionAndAttribution:

    def test_detection_counts_any_non_benign_prediction(self):
        held_pred = np.array([BENIGN, "DoS Hulk", "PortScan", BENIGN], dtype=object)
        report = lofo.detection_report(np.array(["DDoS"] * 4, dtype=object), held_pred)

        assert report["held_out_support"] == 4
        assert report["predicted_attack_count"] == 2
        assert report["predicted_benign_count"] == 2
        assert report["attack_detection_rate"] == 0.5
        assert report["attack_miss_rate"] == 0.5

    def test_detection_and_miss_rates_sum_to_one(self):
        held_pred = np.array([BENIGN] * 3 + ["Bot"] * 7, dtype=object)
        report = lofo.detection_report(np.array(["DDoS"] * 10, dtype=object), held_pred)

        assert report["attack_detection_rate"] + report["attack_miss_rate"] == 1.0

    def test_detection_says_nothing_about_correctness(self):
        report = lofo.detection_report(np.array(["DDoS"], dtype=object),
                                       np.array(["PortScan"], dtype=object))

        assert report["attack_detection_rate"] == 1.0
        assert "says nothing about whether the label was correct" in report["definition"]

    def test_attribution_distribution_sums_to_the_attack_predictions(self):
        held_pred = np.array([BENIGN, "DoS Hulk", "DoS Hulk", "PortScan"], dtype=object)
        report = lofo.attribution_report(held_pred)

        assert report["attack_predictions"] == 3
        assert sum(report["predicted_label_distribution"].values()) == 3
        assert sum(report["predicted_family_distribution"].values()) == 3

    def test_attribution_reports_the_dominant_label_and_family(self):
        held_pred = np.array(["DoS Hulk"] * 7 + ["PortScan"] * 3, dtype=object)
        report = lofo.attribution_report(held_pred)

        assert report["dominant_predicted_label"] == "DoS Hulk"
        assert report["dominant_predicted_family"] == "DoS"
        assert report["dominant_predicted_label_share"] == pytest.approx(0.7)

    def test_attribution_handles_nothing_being_flagged(self):
        report = lofo.attribution_report(np.array([BENIGN, BENIGN], dtype=object))

        assert report["attack_predictions"] == 0
        assert report["dominant_predicted_label"] is None

    def test_attribution_warns_that_a_dominant_label_is_a_misattribution(self):
        report = lofo.attribution_report(np.array(["Bot"], dtype=object))

        assert "misattribution" in report["note"]
