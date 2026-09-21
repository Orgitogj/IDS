package com.diploma.idsml.service;

import com.diploma.idsml.dto.AuthenticatedSession;
import com.diploma.idsml.dto.ChangePasswordRequest;
import com.diploma.idsml.dto.CurrentUserResponse;
import com.diploma.idsml.dto.LoginResponse;
import com.diploma.idsml.dto.RegisterRequest;
import com.diploma.idsml.dto.UserResponse;
import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.exception.InvalidCredentialsException;
import com.diploma.idsml.exception.InvalidRequestException;
import com.diploma.idsml.exception.TooManyAttemptsException;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.security.JwtService;
import com.diploma.idsml.security.LoginAttemptService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);
    private static final String BAD_CREDENTIALS = "Përdoruesi ose fjalëkalimi është i pasaktë.";

    private final AppUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final RefreshTokenService refreshTokenService;
    private final LoginAttemptService loginAttemptService;
    private final LoginStateService loginStateService;

    public AuthService(AppUserRepository userRepository,
                       PasswordEncoder passwordEncoder,
                       JwtService jwtService,
                       RefreshTokenService refreshTokenService,
                       LoginAttemptService loginAttemptService,
                       LoginStateService loginStateService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.refreshTokenService = refreshTokenService;
        this.loginAttemptService = loginAttemptService;
        this.loginStateService = loginStateService;
    }

    public AuthenticatedSession login(String username, String password, String client) {
        loginAttemptService.verifyNotThrottled(client);

        Optional<AppUser> found = userRepository.findByUsername(username);
        if (found.isEmpty()) {
            loginAttemptService.recordFailure(client);
            throw new InvalidCredentialsException(BAD_CREDENTIALS);
        }

        AppUser user = found.get();
        Instant now = Instant.now();

        if (user.isLockedAt(now)) {
            loginAttemptService.recordFailure(client);
            throw new TooManyAttemptsException(
                    "Llogaria është bllokuar përkohësisht pas disa tentativave të dështuara. Provoni përsëri më vonë.",
                    Math.max(Duration.between(now, user.getLockedUntil()).toSeconds(), 1));
        }

        if (!user.isEnabled() || !passwordEncoder.matches(password, user.getPasswordHash())) {
            loginAttemptService.recordFailure(client);
            loginStateService.recordFailure(user.getId());
            throw new InvalidCredentialsException(BAD_CREDENTIALS);
        }

        loginAttemptService.recordSuccess(client);

        return sessionFor(loginStateService.recordSuccess(user.getId(), now));
    }

    @Transactional
    public AuthenticatedSession refresh(String refreshToken) {
        RefreshTokenService.Rotation rotation = refreshTokenService.rotate(refreshToken);
        return new AuthenticatedSession(accessTokenFor(rotation.user()), rotation.refreshToken());
    }

    @Transactional
    public void logout(String refreshToken) {
        refreshTokenService.revoke(refreshToken);
    }

    @Transactional
    public UserResponse register(RegisterRequest request) {
        String username = request.username().trim();

        if (!request.password().equals(request.confirmPassword())) {
            throw new InvalidRequestException("Fjalëkalimet nuk përputhen.");
        }

        if (userRepository.existsByUsernameIgnoreCase(username)) {
            throw new InvalidRequestException("Ky përdorues ekziston tashmë.");
        }

        AppUser user = AppUser.builder()
                .username(username)
                .passwordHash(passwordEncoder.encode(request.password()))
                .role(request.role())
                .build();

        try {
            userRepository.saveAndFlush(user);
        } catch (DataIntegrityViolationException ex) {
            throw new InvalidRequestException("Ky përdorues ekziston tashmë.");
        }

        return UserResponse.from(user);
    }

    @Transactional
    public void changePassword(String username, ChangePasswordRequest request) {
        AppUser user = userRepository.findByUsername(username)
                .orElseThrow(() -> new InvalidCredentialsException(BAD_CREDENTIALS));

        if (!passwordEncoder.matches(request.currentPassword(), user.getPasswordHash())) {
            throw new InvalidCredentialsException("Fjalëkalimi aktual është i pasaktë.");
        }

        if (!request.newPassword().equals(request.confirmPassword())) {
            throw new InvalidRequestException("Fjalëkalimet nuk përputhen.");
        }

        if (passwordEncoder.matches(request.newPassword(), user.getPasswordHash())) {
            throw new InvalidRequestException("Fjalëkalimi i ri duhet të jetë i ndryshëm nga ai aktual.");
        }

        user.setPasswordHash(passwordEncoder.encode(request.newPassword()));
        userRepository.save(user);
        refreshTokenService.revokeAllFor(user);

        log.info("Fjalekalimi u ndryshua per {}. Te gjitha sesionet u anuluan.", username);
    }

    @Transactional(readOnly = true)
    public CurrentUserResponse currentUser(String username) {
        AppUser user = userRepository.findByUsername(username)
                .orElseThrow(() -> new InvalidCredentialsException(BAD_CREDENTIALS));

        return new CurrentUserResponse(
                user.getId(),
                user.getUsername(),
                user.getRole().name(),
                user.getLastLoginAt()
        );
    }

    private AuthenticatedSession sessionFor(AppUser user) {
        return new AuthenticatedSession(accessTokenFor(user), refreshTokenService.issue(user));
    }

    private LoginResponse accessTokenFor(AppUser user) {
        String role = user.getRole().name();
        Instant issuedAt = notBefore(Instant.now(), user.getTokensValidFrom());

        return new LoginResponse(
                jwtService.generateToken(user.getUsername(), role, issuedAt),
                user.getUsername(),
                role,
                jwtService.expirationSeconds()
        );
    }

    private static Instant notBefore(Instant now, Instant cutoff) {
        return cutoff.isAfter(now) ? cutoff : now;
    }
}
