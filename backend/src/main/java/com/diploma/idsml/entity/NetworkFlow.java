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
@Table(name = "network_flows")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class NetworkFlow {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @Enumerated(EnumType.STRING)
    @Column(name = "dataset_source", nullable = false)
    private DatasetSource datasetSource;

    @Column(name = "source_ip")
    private String sourceIp;

    @Column(name = "destination_ip")
    private String destinationIp;

    @Column(name = "source_port")
    private Integer sourcePort;

    @Column(name = "destination_port")
    private Integer destinationPort;

    @Column(name = "protocol")
    private String protocol;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "feature_vector", columnDefinition = "jsonb", nullable = false)
    private Map<String, Object> featureVector;

    @Enumerated(EnumType.STRING)
    @Column(name = "label", nullable = false)
    @Builder.Default
    private FlowLabel label = FlowLabel.UNKNOWN;

    @Column(name = "attack_type")
    private String attackType;

    @Enumerated(EnumType.STRING)
    @Column(name = "predicted_label")
    private FlowLabel predictedLabel;

    @Column(name = "prediction_confidence")
    private Double predictionConfidence;

    @Column(name = "flow_timestamp", nullable = false)
    private Instant flowTimestamp;

    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default
    private Instant createdAt = Instant.now();
}
