package com.diploma.idsml.service;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.RefreshToken;
import com.diploma.idsml.exception.InvalidCredentialsException;
import com.diploma.idsml.repository.RefreshTokenRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Optional;

@Service
public class RefreshTokenService {

    private static final Logger log = LoggerFactory.getLogger(RefreshTokenService.class);
    private static final int TOKEN_BYTES = 32;
    private static final String INVALID_SESSION = "Sesioni nuk është më i vlefshëm. Hyni përsëri.";

    private final RefreshTokenRepository refreshTokenRepository;
    private final SessionRevoker sessionRevoker;
    private final SecureRandom random = new SecureRandom();
    private final Duration lifetime;

    public RefreshTokenService(RefreshTokenRepository refreshTokenRepository,
                               SessionRevoker sessionRevoker,
                               @Value("${ids.security.refresh-expiration-days}") long lifetimeDays) {
        this.refreshTokenRepository = refreshTokenRepository;
        this.sessionRevoker = sessionRevoker;
        this.lifetime = Duration.ofDays(lifetimeDays);
    }

    public record Rotation(AppUser user, String refreshToken) {
    }

    @Transactional
    public String issue(AppUser user) {
        String raw = randomToken();

        refreshTokenRepository.save(RefreshToken.builder()
                .user(user)
                .tokenHash(hash(raw))
                .expiresAt(Instant.now().plus(lifetime))
                .build());

        return raw;
    }

    @Transactional
    public Rotation rotate(String rawToken) {
        RefreshToken stored = lookup(rawToken)
                .orElseThrow(() -> new InvalidCredentialsException(INVALID_SESSION));

        Instant now = Instant.now();
        AppUser user = stored.getUser();

        if (stored.getRevokedAt() != null) {
            log.warn("Token-i i rifreskimit u riperdor per {}. Te gjitha sesionet u anuluan.",
                    user.getUsername());
            sessionRevoker.revokeAllFor(user.getId());
            throw new InvalidCredentialsException(INVALID_SESSION);
        }

        if (!stored.isUsableAt(now) || !user.isEnabled()) {
            throw new InvalidCredentialsException(INVALID_SESSION);
        }

        stored.setRevokedAt(now);

        return new Rotation(user, issue(user));
    }

    @Transactional
    public void revoke(String rawToken) {
        lookup(rawToken)
                .filter(token -> token.getRevokedAt() == null)
                .ifPresent(token -> token.setRevokedAt(Instant.now()));
    }

    @Transactional
    public void revokeAllFor(AppUser user) {
        sessionRevoker.revoke(user);
    }

    @Transactional
    @Scheduled(cron = "${ids.security.refresh-purge-cron}")
    public void purgeExpired() {
        int removed = refreshTokenRepository.deleteExpiredBefore(Instant.now());
        if (removed > 0) {
            log.info("U fshine {} token-a rifreskimi te skaduar.", removed);
        }
    }

    private Optional<RefreshToken> lookup(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            return Optional.empty();
        }
        return refreshTokenRepository.findByTokenHash(hash(rawToken));
    }

    private String randomToken() {
        byte[] material = new byte[TOKEN_BYTES];
        random.nextBytes(material);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(material);
    }

    private static String hash(String rawToken) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(rawToken.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 nuk eshte i disponueshem.", ex);
        }
    }
}
