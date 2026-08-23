package com.diploma.idsml.dto;

import java.util.List;
import java.util.Map;

public record AlarmStatsResponse(
        long totalAlarms,
        Map<String, Long> severityCounts,
        Map<String, Long> statusCounts,
        List<HourlyCount> hourlyCounts
) {
}
