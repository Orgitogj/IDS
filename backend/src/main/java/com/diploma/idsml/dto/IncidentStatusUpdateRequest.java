package com.diploma.idsml.dto;

import com.diploma.idsml.entity.AlarmStatus;
import jakarta.validation.constraints.NotNull;

public record IncidentStatusUpdateRequest(
        @NotNull
        AlarmStatus status
) {
}
