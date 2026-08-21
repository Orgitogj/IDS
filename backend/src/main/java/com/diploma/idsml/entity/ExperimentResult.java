package com.diploma.idsml.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "experiment_results")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ExperimentResult {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "ml_model_id", nullable = false)
    private MLModel mlModel;

    @Column(name = "tested_on_dataset", nullable = false)
    private String testedOnDataset;

    @Column(name = "feature_set_used", columnDefinition = "TEXT")
    private String featureSetUsed;

    @Column(name = "accuracy", nullable = false)
    private Double accuracy;

    @Column(name = "precision_score", nullable = false)
    private Double precisionScore;

    @Column(name = "recall", nullable = false)
    private Double recall;

    @Column(name = "f1_score", nullable = false)
    private Double f1Score;

    @Column(name = "avg_latency_ms")
    private Double avgLatencyMs;

    @Column(name = "sample_size")
    private Long sampleSize;

    @Column(name = "notes", columnDefinition = "TEXT")
    private String notes;

    @Column(name = "ran_at", nullable = false)
    @Builder.Default
    private Instant ranAt = Instant.now();
}
