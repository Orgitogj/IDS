package com.diploma.idsml.dto;

public record AuthenticatedSession(
        LoginResponse response,
        String refreshToken
) {
}
