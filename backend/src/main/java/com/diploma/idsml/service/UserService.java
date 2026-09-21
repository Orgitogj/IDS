package com.diploma.idsml.service;

import com.diploma.idsml.dto.UserResponse;
import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.exception.InvalidRequestException;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AppUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
public class UserService {

    private static final Logger log = LoggerFactory.getLogger(UserService.class);

    private final AppUserRepository userRepository;
    private final RefreshTokenService refreshTokenService;

    public UserService(AppUserRepository userRepository, RefreshTokenService refreshTokenService) {
        this.userRepository = userRepository;
        this.refreshTokenService = refreshTokenService;
    }

    @Transactional(readOnly = true)
    public List<UserResponse> list() {
        return userRepository.findAllByOrderByCreatedAtAsc().stream()
                .map(UserResponse::from)
                .toList();
    }

    @Transactional
    public UserResponse setEnabled(UUID id, boolean enabled, String actingUsername) {
        AppUser user = userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Përdoruesi nuk u gjet."));

        if (user.getUsername().equals(actingUsername) && !enabled) {
            throw new InvalidRequestException("Nuk mund ta çaktivizoni llogarinë tuaj.");
        }

        if (user.isEnabled() == enabled) {
            return UserResponse.from(user);
        }

        user.setEnabled(enabled);

        if (enabled) {
            user.setFailedLoginAttempts(0);
            user.setLockedUntil(null);
            userRepository.save(user);
        } else {
            userRepository.save(user);
            refreshTokenService.revokeAllFor(user);
        }

        log.info("Perdoruesi {} u {} nga {}.", user.getUsername(),
                enabled ? "aktivizua" : "cakivizua", actingUsername);

        return UserResponse.from(user);
    }

    @Transactional
    public UserResponse unlock(UUID id) {
        AppUser user = userRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Përdoruesi nuk u gjet."));

        user.setFailedLoginAttempts(0);
        user.setLockedUntil(null);
        userRepository.save(user);

        return UserResponse.from(user);
    }
}
