package com.diploma.idsml.dto;

import java.time.Instant;
import java.util.UUID;

public record CurrentUserResponse(
        UUID id,
        String username,
        String role,
        Instant lastLoginAt
) {
}
