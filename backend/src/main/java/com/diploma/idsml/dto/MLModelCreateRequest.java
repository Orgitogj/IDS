package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
public record MLModelCreateRequest(

        @NotBlank
        String algorithm,

        @NotBlank
        String name,

        String version,

        String featureVersion,

        @NotBlank
        String trainedOnDataset,

        @NotBlank
        String artifactPath,

        String hyperparameters,

        String featureSet,

        @NotNull
        Instant trainedAt
) {
}