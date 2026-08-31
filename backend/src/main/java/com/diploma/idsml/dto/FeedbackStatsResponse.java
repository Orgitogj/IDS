package com.diploma.idsml.dto;

import java.util.Map;

public record FeedbackStatsResponse(
        long totalFeedback,
        Map<String, Long> verdictCounts,
        double falsePositiveRate,
        Map<String, Map<String, Long>> byModel
) {
}
