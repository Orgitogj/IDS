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
