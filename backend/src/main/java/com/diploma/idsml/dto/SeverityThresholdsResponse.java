package com.diploma.idsml.dto;

import java.time.Instant;

public record SeverityThresholdsResponse(
        Double criticalMin,
        Double highMin,
        Double mediumMin,
        Instant updatedAt
) {
}
