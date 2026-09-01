package com.diploma.idsml.security;

import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class JwtServiceTest {

    private static final String SECRET =
            "ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=";
    private static final String OTHER_SECRET =
            "YW5vdGhlci1zZWNyZXQtdGhhdC1pcy1hbHNvLWxvbmctZW5vdWdoLTI1Ni1iaXQ=";

    private final JwtService jwtService = new JwtService(SECRET, 480);

    @Test
    void generatedTokenParsesBackToTheSameSubjectAndRole() {
        String token = jwtService.generateToken("analyst-1", "ANALYST");

        Optional<Claims> claims = jwtService.parse(token);

        assertThat(claims).isPresent();
        assertThat(claims.get().getSubject()).isEqualTo("analyst-1");
        assertThat(claims.get().get("role", String.class)).isEqualTo("ANALYST");
    }

    @Test
    void tokenCarriesAnExpiryDerivedFromTheConfiguredWindow() {
        Claims claims = jwtService.parse(jwtService.generateToken("admin", "ADMIN")).orElseThrow();

        long lifetimeSeconds =
                (claims.getExpiration().getTime() - claims.getIssuedAt().getTime()) / 1000;

        assertThat(lifetimeSeconds).isEqualTo(480 * 60);
        assertThat(jwtService.expirationSeconds()).isEqualTo(480 * 60);
    }

    @Test
    void expiredTokenIsRejected() {
        JwtService expiring = new JwtService(SECRET, -1);

        assertThat(expiring.parse(expiring.generateToken("admin", "ADMIN"))).isEmpty();
    }

    @Test
    void tokenSignedWithAnotherKeyIsRejected() {
        JwtService attacker = new JwtService(OTHER_SECRET, 480);

        String forged = attacker.generateToken("admin", "ADMIN");

        assertThat(jwtService.parse(forged)).isEmpty();
    }

    @Test
    void tamperedTokenIsRejected() {
        String token = jwtService.generateToken("analyst", "ANALYST");
        String tampered = token.substring(0, token.length() - 3) + "aaa";

        assertThat(jwtService.parse(tampered)).isEmpty();
    }

    @Test
    void garbageIsRejectedWithoutThrowing() {
        assertThat(jwtService.parse("not-a-token")).isEmpty();
        assertThat(jwtService.parse("")).isEmpty();
        assertThat(jwtService.parse("a.b.c")).isEmpty();
    }

    @Test
    void rolesAreNotInterchangeableBetweenTokens() {
        Claims analyst = jwtService.parse(jwtService.generateToken("u", "ANALYST")).orElseThrow();
        Claims admin = jwtService.parse(jwtService.generateToken("u", "ADMIN")).orElseThrow();

        assertThat(analyst.get("role", String.class))
                .isNotEqualTo(admin.get("role", String.class));
    }
}
