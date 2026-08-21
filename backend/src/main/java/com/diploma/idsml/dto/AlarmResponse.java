package com.diploma.idsml.dto;

import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;

import java.time.Instant;
import java.util.UUID;

public record AlarmResponse(
        UUID id,
        UUID networkFlowId,
        AlarmSeverity severity,
        AlarmStatus status,
        Instant createdAt,
        Instant acknowledgedAt,
        Instant resolvedAt
) {
}
