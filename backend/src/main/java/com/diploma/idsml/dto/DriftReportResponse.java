package com.diploma.idsml.dto;

import com.diploma.idsml.entity.DriftStatus;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public record DriftReportResponse(
        UUID id,
        DriftStatus status,
        String featureVersion,
        long observedFlows,
        long acceptedFlows,
        long rejectedFlows,
        int sampleSize,
        double invalidRate,
        int driftedFeatureCount,
        double driftedFraction,
        Integer calibrationWindow,
        List<String> reasons,
        List<String> driftedFeatures,
        Map<String, Object> details,
        Instant generatedAt,
        Instant createdAt
) {
}
