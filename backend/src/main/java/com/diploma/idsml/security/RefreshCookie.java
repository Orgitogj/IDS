package com.diploma.idsml.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
public class RefreshCookie {

    public static final String NAME = "ids_refresh";

    private static final String PATH = "/api/auth";
    private static final String SAME_SITE = "Strict";

    private final boolean secure;
    private final Duration lifetime;

    public RefreshCookie(@Value("${ids.security.cookie-secure}") boolean secure,
                         @Value("${ids.security.refresh-expiration-days}") long lifetimeDays) {
        this.secure = secure;
        this.lifetime = Duration.ofDays(lifetimeDays);
    }

    public ResponseCookie issue(String value) {
        return base(value).maxAge(lifetime).build();
    }

    public ResponseCookie clear() {
        return base("").maxAge(Duration.ZERO).build();
    }

    public Duration lifetime() {
        return lifetime;
    }

    private ResponseCookie.ResponseCookieBuilder base(String value) {
        return ResponseCookie.from(NAME, value)
                .httpOnly(true)
                .secure(secure)
                .sameSite(SAME_SITE)
                .path(PATH);
    }
}
