package com.diploma.idsml.dto;

public record LoginResponse(
        String token,
        String username,
        String role,
        long expiresInSeconds
) {
}
