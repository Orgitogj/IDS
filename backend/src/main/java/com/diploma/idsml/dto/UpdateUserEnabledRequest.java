package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotNull;

public record UpdateUserEnabledRequest(
        @NotNull(message = "Fusha 'enabled' eshte e detyrueshme.")
        Boolean enabled
) {
}
