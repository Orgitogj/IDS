package com.diploma.idsml.security;

import com.diploma.idsml.exception.TooManyAttemptsException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class LoginAttemptService {

    private static final String UNKNOWN_CLIENT = "unknown";

    private final int maxAttempts;
    private final Duration window;
    private final Map<String, Attempts> byClient = new ConcurrentHashMap<>();

    public LoginAttemptService(@Value("${ids.security.login.max-ip-attempts}") int maxAttempts,
                               @Value("${ids.security.login.ip-window-minutes}") long windowMinutes) {
        this.maxAttempts = maxAttempts;
        this.window = Duration.ofMinutes(windowMinutes);
    }

    public void verifyNotThrottled(String client) {
        Attempts attempts = byClient.get(key(client));
        if (attempts == null) {
            return;
        }

        Instant now = Instant.now();
        synchronized (attempts) {
            Instant windowEnd = attempts.startedAt.plus(window);
            if (windowEnd.isBefore(now)) {
                return;
            }
            if (attempts.count >= maxAttempts) {
                long retryAfter = Duration.between(now, windowEnd).toSeconds();
                throw new TooManyAttemptsException(
                        "Shumë tentativa hyrjeje nga kjo adresë. Provoni përsëri më vonë.",
                        Math.max(retryAfter, 1));
            }
        }
    }

    public void recordFailure(String client) {
        Instant now = Instant.now();
        byClient.compute(key(client), (ignored, attempts) -> {
            if (attempts == null || attempts.startedAt.plus(window).isBefore(now)) {
                return new Attempts(now);
            }
            synchronized (attempts) {
                attempts.count++;
            }
            return attempts;
        });
    }

    public void recordSuccess(String client) {
        byClient.remove(key(client));
    }

    @Scheduled(fixedDelayString = "${ids.security.login.purge-interval-ms}")
    public void purgeStaleWindows() {
        Instant threshold = Instant.now().minus(window);
        byClient.values().removeIf(attempts -> attempts.startedAt.isBefore(threshold));
    }

    private static String key(String client) {
        return client == null || client.isBlank() ? UNKNOWN_CLIENT : client;
    }

    private static final class Attempts {

        private final Instant startedAt;
        private int count;

        private Attempts(Instant startedAt) {
            this.startedAt = startedAt;
            this.count = 1;
        }
    }
}
