package com.diploma.idsml.dto;

import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.FlowLabel;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record NetworkFlowResponse(
        UUID id,
        DatasetSource datasetSource,
        String sourceIp,
        String destinationIp,
        Integer sourcePort,
        Integer destinationPort,
        String protocol,
        Map<String, Object> featureVector,
        FlowLabel label,
        String attackType,
        String groundTruthAttackType,
        FlowLabel predictedLabel,
        Double predictionConfidence,
        UUID modelId,
        String modelName,
        String modelVersion,
        String featureVersion,
        DetectionMethod detectionMethod,
        Double anomalyScore,
        Instant flowTimestamp,
        Instant createdAt
) {
}
