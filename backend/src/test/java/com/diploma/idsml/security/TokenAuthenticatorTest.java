package com.diploma.idsml.security;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.UserRole;
import com.diploma.idsml.repository.AppUserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@ExtendWith(MockitoExtension.class)
class TokenAuthenticatorTest {

    private static final String SECRET =
            "ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=";

    @Mock
    private AppUserRepository userRepository;

    private JwtService jwtService;
    private TokenAuthenticator tokenAuthenticator;

    @BeforeEach
    void setUp() {
        jwtService = new JwtService(SECRET, 15);
        tokenAuthenticator = new TokenAuthenticator(jwtService, userRepository);
    }

    private static AppUser user(UserRole role) {
        return AppUser.builder()
                .username("analyst-1")
                .passwordHash("stub")
                .role(role)
                .enabled(true)
                .tokensValidFrom(Instant.now().minus(1, ChronoUnit.HOURS))
                .build();
    }

    private static List<String> authoritiesOf(UsernamePasswordAuthenticationToken authentication) {
        return authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();
    }

    @Test
    void aValidTokenForAnEnabledUserAuthenticates() {
        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.of(user(UserRole.ANALYST)));

        String token = jwtService.generateToken("analyst-1", "ANALYST");

        Optional<UsernamePasswordAuthenticationToken> authentication =
                tokenAuthenticator.authenticate(token);

        assertThat(authentication).isPresent();
        assertThat(authentication.get().getName()).isEqualTo("analyst-1");
        assertThat(authoritiesOf(authentication.get())).containsExactly("ROLE_ANALYST");
    }

    @Test
    void aDisabledUserIsRejectedEvenWithASignedToken() {
        AppUser disabled = user(UserRole.ANALYST);
        disabled.setEnabled(false);
        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.of(disabled));

        String token = jwtService.generateToken("analyst-1", "ANALYST");

        assertThat(tokenAuthenticator.authenticate(token)).isEmpty();
    }

    @Test
    void aDeletedUserIsRejectedEvenWithASignedToken() {
        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.empty());

        String token = jwtService.generateToken("analyst-1", "ANALYST");

        assertThat(tokenAuthenticator.authenticate(token)).isEmpty();
    }

    @Test
    void aTokenIssuedBeforeTheLastRevocationIsRejected() {
        String token = jwtService.generateToken("analyst-1", "ANALYST");

        AppUser revoked = user(UserRole.ANALYST);
        revoked.setTokensValidFrom(Instant.now().plus(1, ChronoUnit.MINUTES));
        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.of(revoked));

        assertThat(tokenAuthenticator.authenticate(token)).isEmpty();
    }

    @Test
    void theRoleComesFromTheDatabaseNotFromTheTokenClaim() {
        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.of(user(UserRole.ANALYST)));

        String escalated = jwtService.generateToken("analyst-1", "ADMIN");

        Optional<UsernamePasswordAuthenticationToken> authentication =
                tokenAuthenticator.authenticate(escalated);

        assertThat(authentication).isPresent();
        assertThat(authoritiesOf(authentication.get())).containsExactly("ROLE_ANALYST");
    }

    @Test
    void aRoleDowngradeInTheDatabaseTakesEffectImmediately() {
        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.of(user(UserRole.ADMIN)));

        String token = jwtService.generateToken("analyst-1", "ANALYST");

        assertThat(authoritiesOf(tokenAuthenticator.authenticate(token).orElseThrow()))
                .containsExactly("ROLE_ADMIN");
    }

    @Test
    void aForgedTokenNeverReachesTheDatabase() {
        JwtService attacker = new JwtService(
                "YW5vdGhlci1zZWNyZXQtdGhhdC1pcy1hbHNvLWxvbmctZW5vdWdoLTI1Ni1iaXQ=", 15);

        assertThat(tokenAuthenticator.authenticate(attacker.generateToken("analyst-1", "ADMIN")))
                .isEmpty();
    }
}
