package com.diploma.idsml.security;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.repository.AppUserRepository;
import io.jsonwebtoken.Claims;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Optional;

@Component
public class TokenAuthenticator {

    private final JwtService jwtService;
    private final AppUserRepository userRepository;

    public TokenAuthenticator(JwtService jwtService, AppUserRepository userRepository) {
        this.jwtService = jwtService;
        this.userRepository = userRepository;
    }

    @Transactional(readOnly = true)
    public Optional<UsernamePasswordAuthenticationToken> authenticate(String token) {
        return jwtService.parse(token).flatMap(this::resolve);
    }

    private Optional<UsernamePasswordAuthenticationToken> resolve(Claims claims) {
        String username = claims.getSubject();
        if (username == null || username.isBlank()) {
            return Optional.empty();
        }

        return userRepository.findByUsername(username)
                .filter(AppUser::isEnabled)
                .filter(user -> issuedAfterLastRevocation(claims, user))
                .map(TokenAuthenticator::authenticationFor);
    }

    private static boolean issuedAfterLastRevocation(Claims claims, AppUser user) {
        Date issuedAt = claims.getIssuedAt();
        if (issuedAt == null) {
            return false;
        }

        Instant cutoff = user.getTokensValidFrom().truncatedTo(ChronoUnit.SECONDS);
        return !issuedAt.toInstant().isBefore(cutoff);
    }

    private static UsernamePasswordAuthenticationToken authenticationFor(AppUser user) {
        return new UsernamePasswordAuthenticationToken(
                user.getUsername(),
                null,
                List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole().name()))
        );
    }
}
