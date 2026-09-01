package com.diploma.idsml.service;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.repository.RefreshTokenRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Service
public class SessionRevoker {

    private final RefreshTokenRepository refreshTokenRepository;
    private final AppUserRepository userRepository;

    public SessionRevoker(RefreshTokenRepository refreshTokenRepository,
                          AppUserRepository userRepository) {
        this.refreshTokenRepository = refreshTokenRepository;
        this.userRepository = userRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void revokeAllFor(UUID userId) {
        userRepository.findById(userId).ifPresent(this::revoke);
    }

    @Transactional
    public void revoke(AppUser user) {
        Instant now = Instant.now();
        refreshTokenRepository.revokeAllForUser(user, now);
        user.setTokensValidFrom(nextWholeSecond(now));
        userRepository.save(user);
    }

    private static Instant nextWholeSecond(Instant moment) {
        return moment.truncatedTo(ChronoUnit.SECONDS).plusSeconds(1);
    }
}
