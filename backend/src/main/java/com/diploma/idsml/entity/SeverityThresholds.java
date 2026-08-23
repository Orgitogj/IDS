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
@Table(name = "severity_thresholds")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SeverityThresholds {

    public static final UUID SINGLETON_ID =
            UUID.fromString("00000000-0000-0000-0000-000000000001");

    @Id
    @Builder.Default
    private UUID id = SINGLETON_ID;

    @Column(name = "critical_min", nullable = false)
    private Double criticalMin;

    @Column(name = "high_min", nullable = false)
    private Double highMin;

    @Column(name = "medium_min", nullable = false)
    private Double mediumMin;

    @Column(name = "updated_at", nullable = false)
    @Builder.Default
    private Instant updatedAt = Instant.now();
}
