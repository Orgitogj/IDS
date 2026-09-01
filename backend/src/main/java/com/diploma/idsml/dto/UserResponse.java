package com.diploma.idsml.dto;

import com.diploma.idsml.entity.AppUser;

import java.time.Instant;
import java.util.UUID;

public record UserResponse(
        UUID id,
        String username,
        String role,
        boolean enabled,
        Instant createdAt,
        Instant lastLoginAt,
        Instant lockedUntil
) {

    public static UserResponse from(AppUser user) {
        return new UserResponse(
                user.getId(),
                user.getUsername(),
                user.getRole().name(),
                user.isEnabled(),
                user.getCreatedAt(),
                user.getLastLoginAt(),
                user.isLockedAt(Instant.now()) ? user.getLockedUntil() : null
        );
    }
}
