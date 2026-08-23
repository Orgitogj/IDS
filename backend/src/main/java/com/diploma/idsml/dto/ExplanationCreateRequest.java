package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotBlank;

public record ExplanationCreateRequest(
        @NotBlank String explanationText,
        @NotBlank String llmModel,
        @NotBlank String llmPromptVersion,
        Double generationLatencyMs
) {
}