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
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "incidents")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Incident {

    public static final int MAX_TRACKED_DESTINATIONS = 100;

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @Column(name = "correlation_key", nullable = false)
    private String correlationKey;

    @Column(name = "source_ip")
    private String sourceIp;

    @Column(name = "attack_type")
    private String attackType;

    @Enumerated(EnumType.STRING)
    @Column(name = "detection_method")
    private DetectionMethod detectionMethod;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "destination_ips", columnDefinition = "jsonb", nullable = false)
    @Builder.Default
    private List<String> destinationIps = new ArrayList<>();

    @Column(name = "destinations_truncated", nullable = false)
    @Builder.Default
    private boolean destinationsTruncated = false;

    @Column(name = "first_seen", nullable = false)
    private Instant firstSeen;

    @Column(name = "last_seen", nullable = false)
    private Instant lastSeen;

    @Column(name = "flow_count", nullable = false)
    @Builder.Default
    private long flowCount = 0;

    @Column(name = "alarm_count", nullable = false)
    @Builder.Default
    private long alarmCount = 0;

    @Enumerated(EnumType.STRING)
    @Column(name = "severity", nullable = false)
    private AlarmSeverity severity;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    @Builder.Default
    private AlarmStatus status = AlarmStatus.NEW;

    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default
    private Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    @Builder.Default
    private Instant updatedAt = Instant.now();

    public boolean isOpen() {
        return status != AlarmStatus.RESOLVED && status != AlarmStatus.FALSE_POSITIVE;
    }

    public void trackDestination(String destinationIp) {
        if (destinationIp == null || destinationIps.contains(destinationIp)) {
            return;
        }
        if (destinationIps.size() >= MAX_TRACKED_DESTINATIONS) {
            destinationsTruncated = true;
            return;
        }
        destinationIps.add(destinationIp);
    }
}
