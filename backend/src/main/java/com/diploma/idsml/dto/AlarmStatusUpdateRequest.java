package com.diploma.idsml.dto;

import com.diploma.idsml.entity.AlarmStatus;
import jakarta.validation.constraints.NotNull;

public record AlarmStatusUpdateRequest(
        @NotNull
        AlarmStatus status
) {
}
