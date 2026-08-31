package com.diploma.idsml.dto;

import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.DetectionMethod;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record IncidentResponse(
        UUID id,
        String correlationKey,
        String sourceIp,
        String attackType,
        DetectionMethod detectionMethod,
        List<String> destinationIps,
        boolean destinationsTruncated,
        long destinationCount,
        Instant firstSeen,
        Instant lastSeen,
        long flowCount,
        long alarmCount,
        AlarmSeverity severity,
        AlarmStatus status,
        Instant createdAt,
        Instant updatedAt
) {
}
