package com.diploma.idsml.dto;

import com.diploma.idsml.entity.DatasetSource;
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
        FlowLabel predictedLabel,
        Double predictionConfidence,
        Instant flowTimestamp,
        Instant createdAt
) {
}
