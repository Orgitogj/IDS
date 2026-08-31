package com.diploma.idsml.dto;

public record AlarmGroupResponse(
        String sourceIp,
        String attackType,
        long alarmCount,
        String topSeverity,
        String firstSeen,
        String lastSeen
) {
}
