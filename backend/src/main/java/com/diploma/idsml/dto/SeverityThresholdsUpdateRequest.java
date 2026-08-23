package com.diploma.idsml.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

public record SeverityThresholdsUpdateRequest(
        @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double criticalMin,
        @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double highMin,
        @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double mediumMin
) {
}
