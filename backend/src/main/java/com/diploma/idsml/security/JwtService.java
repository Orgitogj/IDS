package com.diploma.idsml.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;
import java.util.UUID;

@Service
public class JwtService {

    private static final Logger log = LoggerFactory.getLogger(JwtService.class);
    private static final int KEY_BYTES = 32;

    private final SecretKey key;
    private final Duration expiration;

    public JwtService(@Value("${ids.security.jwt-secret:}") String secret,
                      @Value("${ids.security.jwt-expiration-minutes}") long expirationMinutes) {
        this.key = secret.isBlank()
                ? ephemeralKey()
                : Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expiration = Duration.ofMinutes(expirationMinutes);
    }

    private static SecretKey ephemeralKey() {
        byte[] material = new byte[KEY_BYTES];
        new SecureRandom().nextBytes(material);
        log.warn("IDS_JWT_SECRET nuk eshte vendosur. U gjenerua nje celes i perkohshem: "
                + "te gjitha token-at behen te pavlefshme pas rinisjes se serverit.");
        return Keys.hmacShaKeyFor(material);
    }

    public String generateToken(String username, String role) {
        return generateToken(username, role, Instant.now());
    }

    public String generateToken(String username, String role, Instant issuedAt) {
        return Jwts.builder()
                .id(UUID.randomUUID().toString())
                .subject(username)
                .claim("role", role)
                .issuedAt(Date.from(issuedAt))
                .expiration(Date.from(issuedAt.plus(expiration)))
                .signWith(key, Jwts.SIG.HS256)
                .compact();
    }

    public Optional<Claims> parse(String token) {
        try {
            return Optional.of(Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload());
        } catch (JwtException | IllegalArgumentException ex) {
            return Optional.empty();
        }
    }

    public long expirationSeconds() {
        return expiration.toSeconds();
    }
}
