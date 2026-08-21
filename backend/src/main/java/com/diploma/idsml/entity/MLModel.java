package com.diploma.idsml.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "ml_models")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MLModel {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @Column(name = "algorithm", nullable = false)
    private String algorithm;

    @Column(name = "name", nullable = false, unique = true)
    private String name;

    @Column(name = "trained_on_dataset", nullable = false)
    private String trainedOnDataset;

    @Column(name = "artifact_path", nullable = false)
    private String artifactPath;

    @Column(name = "hyperparameters", columnDefinition = "TEXT")
    private String hyperparameters;

    @Column(name = "feature_set", columnDefinition = "TEXT")
    private String featureSet;

    @Column(name = "active", nullable = false)
    @Builder.Default
    private boolean active = false;

    @Column(name = "trained_at", nullable = false)
    private Instant trainedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default
    private Instant createdAt = Instant.now();
}
