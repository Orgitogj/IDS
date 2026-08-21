package com.diploma.idsml.dto;

import java.time.Instant;
import java.util.UUID;

public record ExplanationResponse(
        UUID id,
        UUID alarmId,
        String explanationText,
        String llmModel,
        String llmPromptVersion,
        Instant generatedAt
) {
}
