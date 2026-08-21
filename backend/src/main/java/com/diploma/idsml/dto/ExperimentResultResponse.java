package com.diploma.idsml.dto;

import java.time.Instant;
import java.util.UUID;

public record ExperimentResultResponse(
        UUID id,
        UUID mlModelId,
        String mlModelName,
        String testedOnDataset,
        String featureSetUsed,
        Double accuracy,
        Double precisionScore,
        Double recall,
        Double f1Score,
        Double avgLatencyMs,
        Long sampleSize,
        String notes,
        Instant ranAt
) {
}
