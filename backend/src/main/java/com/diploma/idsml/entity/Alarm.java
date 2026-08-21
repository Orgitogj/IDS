package com.diploma.idsml.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "alarms")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Alarm {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @OneToOne
    @JoinColumn(name = "network_flow_id", nullable = false, unique = true)
    private NetworkFlow networkFlow;

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

    @Column(name = "acknowledged_at")
    private Instant acknowledgedAt;

    @Column(name = "resolved_at")
    private Instant resolvedAt;
}
