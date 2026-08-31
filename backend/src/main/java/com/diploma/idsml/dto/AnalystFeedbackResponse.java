package com.diploma.idsml.dto;

import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.FlowLabel;

import java.time.Instant;
import java.util.UUID;

public record AnalystFeedbackResponse(
        UUID id,
        UUID alarmId,
        UUID networkFlowId,
        UUID incidentId,
        FlowLabel originalPrediction,
        String originalAttackType,
        Double originalConfidence,
        Double originalAnomalyScore,
        DetectionMethod detectionMethod,
        AlarmStatus analystVerdict,
        String analystAttackType,
        String analystUsername,
        String notes,
        UUID modelId,
        String modelName,
        String modelVersion,
        String featureVersion,
        String groundTruthLabel,
        Instant createdAt
) {
}
