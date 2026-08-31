package com.diploma.idsml.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Entity
@Table(name = "drift_reports")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DriftReport {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private DriftStatus status;

    @Column(name = "feature_version")
    private String featureVersion;

    @Column(name = "observed_flows", nullable = false)
    private long observedFlows;

    @Column(name = "accepted_flows", nullable = false)
    private long acceptedFlows;

    @Column(name = "rejected_flows", nullable = false)
    private long rejectedFlows;

    @Column(name = "sample_size", nullable = false)
    private int sampleSize;

    @Column(name = "invalid_rate", nullable = false)
    private double invalidRate;

    @Column(name = "drifted_feature_count", nullable = false)
    private int driftedFeatureCount;

    @Column(name = "drifted_fraction", nullable = false)
    private double driftedFraction;

    @Column(name = "calibration_window")
    private Integer calibrationWindow;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "reasons", columnDefinition = "jsonb", nullable = false)
    @Builder.Default
    private List<String> reasons = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "drifted_features", columnDefinition = "jsonb", nullable = false)
    @Builder.Default
    private List<String> driftedFeatures = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "details", columnDefinition = "jsonb", nullable = false)
    @Builder.Default
    private Map<String, Object> details = new LinkedHashMap<>();

    @Column(name = "generated_at", nullable = false)
    private Instant generatedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default
    private Instant createdAt = Instant.now();
}
