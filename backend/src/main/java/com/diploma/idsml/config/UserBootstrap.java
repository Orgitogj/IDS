package com.diploma.idsml.config;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.UserRole;
import com.diploma.idsml.repository.AppUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.util.Base64;

@Component
public class UserBootstrap implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(UserBootstrap.class);
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int PASSWORD_BYTES = 18;

    private final AppUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final String adminUsername;
    private final String adminPassword;
    private final String serviceUsername;
    private final String servicePassword;

    public UserBootstrap(AppUserRepository userRepository,
                         PasswordEncoder passwordEncoder,
                         @Value("${ids.bootstrap.admin-username}") String adminUsername,
                         @Value("${ids.bootstrap.admin-password:}") String adminPassword,
                         @Value("${ids.bootstrap.service-username}") String serviceUsername,
                         @Value("${ids.bootstrap.service-password:}") String servicePassword) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.adminUsername = adminUsername;
        this.adminPassword = adminPassword;
        this.serviceUsername = serviceUsername;
        this.servicePassword = servicePassword;
    }

    @Override
    public void run(String... args) {
        createIfAbsent(adminUsername, adminPassword, UserRole.ADMIN, "IDS_ADMIN_PASSWORD");
        createIfAbsent(serviceUsername, servicePassword, UserRole.SERVICE, "IDS_SERVICE_PASSWORD");
    }

    private void createIfAbsent(String username, String configured, UserRole role, String envVar) {
        if (userRepository.findByUsername(username).isPresent()) {
            return;
        }

        boolean generated = configured.isBlank();
        String rawPassword = generated ? randomPassword() : configured;

        userRepository.save(AppUser.builder()
                .username(username)
                .passwordHash(passwordEncoder.encode(rawPassword))
                .role(role)
                .build());

        log.info("Perdoruesi fillestar u krijua: {} ({})", username, role);

        if (generated) {
            log.warn("{} nuk eshte vendosur. Fjalekalimi i gjeneruar per '{}' eshte: {} "
                            + "- ruajeni tani, nuk shfaqet perseri.",
                    envVar, username, rawPassword);
        }
    }

    private static String randomPassword() {
        byte[] material = new byte[PASSWORD_BYTES];
        RANDOM.nextBytes(material);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(material);
    }
}
