package com.diploma.idsml.service;

import com.diploma.idsml.dto.LoginResponse;
import com.diploma.idsml.dto.RegisterRequest;
import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.UserRole;
import com.diploma.idsml.exception.InvalidCredentialsException;
import com.diploma.idsml.exception.InvalidRequestException;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.security.JwtService;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private final AppUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;

    public AuthService(AppUserRepository userRepository,
                       PasswordEncoder passwordEncoder,
                       JwtService jwtService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
    }

    public LoginResponse login(String username, String password) {
        AppUser user = userRepository.findByUsername(username)
                .orElseThrow(() -> new InvalidCredentialsException("Kredenciale te pasakta."));

        if (!user.isEnabled() || !passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new InvalidCredentialsException("Kredenciale te pasakta.");
        }

        return tokenFor(user);
    }

    @Transactional
    public LoginResponse register(RegisterRequest request) {
        String username = request.username().trim();

        if (!request.password().equals(request.confirmPassword())) {
            throw new InvalidRequestException("Fjalekalimet nuk perputhen.");
        }

        if (userRepository.existsByUsernameIgnoreCase(username)) {
            throw new InvalidRequestException("Ky perdorues ekziston tashme.");
        }

        AppUser user = AppUser.builder()
                .username(username)
                .passwordHash(passwordEncoder.encode(request.password()))
                .role(UserRole.ANALYST)
                .build();

        try {
            userRepository.saveAndFlush(user);
        } catch (DataIntegrityViolationException ex) {
            throw new InvalidRequestException("Ky perdorues ekziston tashme.");
        }

        return tokenFor(user);
    }

    private LoginResponse tokenFor(AppUser user) {
        String role = user.getRole().name();
        return new LoginResponse(
                jwtService.generateToken(user.getUsername(), role),
                user.getUsername(),
                role,
                jwtService.expirationSeconds()
        );
    }
}
