package com.diploma.idsml.dto;

import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.FlowLabel;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

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

        Double predictionConfidence,

        String attackType,

        FlowLabel groundTruthLabel,

        String groundTruthAttackType,

        UUID modelId,

        String modelName,

        String modelVersion,

        String featureVersion,

        DetectionMethod detectionMethod,

        Double anomalyScore,

        @NotNull
        Instant flowTimestamp,

        DatasetSource datasetSource
) {
}
