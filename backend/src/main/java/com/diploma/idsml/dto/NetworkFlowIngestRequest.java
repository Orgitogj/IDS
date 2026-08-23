package com.diploma.idsml.dto;

import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.FlowLabel;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.Instant;
import java.util.Map;

public record NetworkFlowIngestRequest(

        @NotBlank
        String sourceIp,

        @NotBlank
        String destinationIp,

        Integer sourcePort,

        Integer destinationPort,

        String protocol,

        @NotNull
        Map<String, Object> featureVector,

        @NotNull
        FlowLabel predictedLabel,

        @NotNull
        Double predictionConfidence,

        String attackType,

        @NotNull
        Instant flowTimestamp,

        DatasetSource datasetSource
) {
}
