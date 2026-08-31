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
import java.util.Map;
import java.util.UUID;

@Entity
@Table(name = "analyst_feedback")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AnalystFeedback {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @Column(name = "alarm_id", nullable = false)
    private UUID alarmId;

    @Column(name = "network_flow_id", nullable = false)
    private UUID networkFlowId;

    @Column(name = "incident_id")
    private UUID incidentId;

    @Enumerated(EnumType.STRING)
    @Column(name = "original_prediction", nullable = false)
    private FlowLabel originalPrediction;

    @Column(name = "original_attack_type")
    private String originalAttackType;

    @Column(name = "original_confidence")
    private Double originalConfidence;

    @Column(name = "original_anomaly_score")
    private Double originalAnomalyScore;

    @Enumerated(EnumType.STRING)
    @Column(name = "detection_method")
    private DetectionMethod detectionMethod;

    @Enumerated(EnumType.STRING)
    @Column(name = "analyst_verdict", nullable = false)
    private AlarmStatus analystVerdict;

    @Column(name = "analyst_attack_type")
    private String analystAttackType;

    @Column(name = "analyst_username", nullable = false)
    private String analystUsername;

    @Column(name = "notes", columnDefinition = "TEXT")
    private String notes;

    @Column(name = "model_id")
    private UUID modelId;

    @Column(name = "model_name")
    private String modelName;

    @Column(name = "model_version")
    private String modelVersion;

    @Column(name = "feature_version")
    private String featureVersion;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "feature_vector", columnDefinition = "jsonb", nullable = false)
    private Map<String, Object> featureVector;

    @Column(name = "ground_truth_label")
    private String groundTruthLabel;

    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default
    private Instant createdAt = Instant.now();
}
