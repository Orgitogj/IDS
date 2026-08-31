package com.diploma.idsml.dto;

import com.diploma.idsml.entity.DriftStatus;
import jakarta.validation.constraints.NotNull;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record DriftReportCreateRequest(
        @NotNull
        DriftStatus status,

        String featureVersion,

        @NotNull
        Long observedFlows,

        @NotNull
        Long acceptedFlows,

        @NotNull
        Long rejectedFlows,

        @NotNull
        Integer sampleSize,

        @NotNull
        Double invalidRate,

        @NotNull
        Integer driftedFeatureCount,

        @NotNull
        Double driftedFraction,

        Integer calibrationWindow,

        List<String> reasons,

        List<String> driftedFeatures,

        Map<String, Object> features,

        @NotNull
        Instant generatedAt
) {
}
