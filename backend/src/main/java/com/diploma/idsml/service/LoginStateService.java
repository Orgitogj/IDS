package com.diploma.idsml.service;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.repository.AppUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Service
public class LoginStateService {

    private static final Logger log = LoggerFactory.getLogger(LoginStateService.class);

    private final AppUserRepository userRepository;
    private final int maxAttempts;
    private final Duration lockWindow;

    public LoginStateService(AppUserRepository userRepository,
                             @Value("${ids.security.login.max-user-attempts}") int maxAttempts,
                             @Value("${ids.security.login.user-lock-minutes}") long lockMinutes) {
        this.userRepository = userRepository;
        this.maxAttempts = maxAttempts;
        this.lockWindow = Duration.ofMinutes(lockMinutes);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(UUID userId) {
        Optional<AppUser> found = userRepository.findById(userId);
        if (found.isEmpty()) {
            return;
        }

        AppUser user = found.get();
        int attempts = user.getFailedLoginAttempts() + 1;
        user.setFailedLoginAttempts(attempts);

        if (attempts >= maxAttempts) {
            user.setFailedLoginAttempts(0);
            user.setLockedUntil(Instant.now().plus(lockWindow));
            log.warn("Llogaria {} u bllokua deri me {} pas {} perpjekjeve te deshtuara.",
                    user.getUsername(), user.getLockedUntil(), maxAttempts);
        }

        userRepository.save(user);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AppUser recordSuccess(UUID userId, Instant at) {
        AppUser user = userRepository.findById(userId).orElseThrow();

        user.setFailedLoginAttempts(0);
        user.setLockedUntil(null);
        user.setLastLoginAt(at);

        return userRepository.save(user);
    }
}
