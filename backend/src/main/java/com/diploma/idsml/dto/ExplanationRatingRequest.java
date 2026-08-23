package com.diploma.idsml.dto;

import com.diploma.idsml.entity.ExplanationRating;
import jakarta.validation.constraints.NotNull;

public record ExplanationRatingRequest(
        @NotNull
        ExplanationRating rating
) {
}
