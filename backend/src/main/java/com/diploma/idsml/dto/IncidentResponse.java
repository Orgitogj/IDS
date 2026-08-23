package com.diploma.idsml.dto;

public record IncidentResponse(
        String sourceIp,
        String attackType,
        long alarmCount,
        String topSeverity,
        String firstSeen,
        String lastSeen
) {
}
