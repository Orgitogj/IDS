package com.diploma.idsml.support;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.UserRole;
import com.diploma.idsml.repository.AppUserRepository;

import java.time.Instant;
import java.util.Locale;
import java.util.Optional;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;

public final class AuthTestSupport {

    private AuthTestSupport() {
    }

    public static String usernameFor(String role) {
        return role.toLowerCase(Locale.ROOT);
    }

    public static void stubRoleNamedUsers(AppUserRepository userRepository) {
        given(userRepository.findByUsername(anyString())).willAnswer(invocation ->
                userNamed(invocation.getArgument(0)));
    }

    private static Optional<AppUser> userNamed(String username) {
        try {
            return Optional.of(AppUser.builder()
                    .username(username)
                    .passwordHash("stub")
                    .role(UserRole.valueOf(username.toUpperCase(Locale.ROOT)))
                    .enabled(true)
                    .tokensValidFrom(Instant.EPOCH)
                    .build());
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }
    }
}
