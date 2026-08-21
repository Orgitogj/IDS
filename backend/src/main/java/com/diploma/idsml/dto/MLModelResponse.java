package com.diploma.idsml.dto;

import java.time.Instant;
import java.util.UUID;

public record MLModelResponse(
        UUID id,
        String algorithm,
        String name,
        String trainedOnDataset,
        String artifactPath,
        String hyperparameters,
        String featureSet,
        boolean active,
        Instant trainedAt,
        Instant createdAt
) {
}
