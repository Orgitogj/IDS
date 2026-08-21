package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record ExperimentResultCreateRequest(

        @NotNull
        UUID mlModelId,

        @NotBlank
        String testedOnDataset,

        String featureSetUsed,

        @NotNull
        Double accuracy,

        @NotNull
        Double precisionScore,

        @NotNull
        Double recall,

        @NotNull
        Double f1Score,

        Double avgLatencyMs,

        Long sampleSize,

        String notes
) {
}