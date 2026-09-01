package com.diploma.idsml.service;

import com.diploma.idsml.dto.AuthenticatedSession;
import com.diploma.idsml.dto.ChangePasswordRequest;
import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.UserRole;
import com.diploma.idsml.exception.InvalidCredentialsException;
import com.diploma.idsml.exception.InvalidRequestException;
import com.diploma.idsml.exception.TooManyAttemptsException;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.security.JwtService;
import com.diploma.idsml.security.LoginAttemptService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class AuthServiceTest {

    private static final String SECRET =
            "ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=";
    private static final String CLIENT = "10.0.0.9";
    private static final String PASSWORD = "correct-horse-1";

    @Mock
    private AppUserRepository userRepository;

    @Mock
    private RefreshTokenService refreshTokenService;

    private PasswordEncoder passwordEncoder;
    private JwtService jwtService;
    private LoginAttemptService loginAttemptService;
    private LoginStateService loginStateService;
    private AuthService authService;
    private AppUser user;

    @BeforeEach
    void setUp() {
        passwordEncoder = new BCryptPasswordEncoder();
        loginAttemptService = new LoginAttemptService(20, 5);

        user = AppUser.builder()
                .username("analyst-1")
                .passwordHash(passwordEncoder.encode(PASSWORD))
                .role(UserRole.ANALYST)
                .enabled(true)
                .build();

        jwtService = new JwtService(SECRET, 15);
        loginStateService = new LoginStateService(userRepository, 3, 15);
        authService = new AuthService(userRepository, passwordEncoder, jwtService,
                refreshTokenService, loginAttemptService, loginStateService);

        given(userRepository.findByUsername("analyst-1")).willReturn(Optional.of(user));
        given(userRepository.findById(user.getId())).willReturn(Optional.of(user));
        given(userRepository.save(any())).willAnswer(invocation -> invocation.getArgument(0));
        given(refreshTokenService.issue(any())).willReturn("refresh-token-value");
    }

    @Test
    void aSuccessfulLoginReturnsAnAccessTokenAndARefreshToken() {
        AuthenticatedSession session = authService.login("analyst-1", PASSWORD, CLIENT);

        assertThat(session.response().token()).isNotBlank();
        assertThat(session.response().role()).isEqualTo("ANALYST");
        assertThat(session.refreshToken()).isEqualTo("refresh-token-value");
        assertThat(user.getLastLoginAt()).isNotNull();
        assertThat(user.getFailedLoginAttempts()).isZero();
    }

    @Test
    void repeatedFailuresLockTheAccountAndFurtherAttemptsAreThrottled() {
        for (int attempt = 0; attempt < 3; attempt++) {
            assertThatThrownBy(() -> authService.login("analyst-1", "wrong", CLIENT))
                    .isInstanceOf(InvalidCredentialsException.class);
        }

        assertThat(user.getLockedUntil()).isNotNull();

        assertThatThrownBy(() -> authService.login("analyst-1", PASSWORD, CLIENT))
                .isInstanceOf(TooManyAttemptsException.class);
    }

    @Test
    void theCorrectPasswordIsRefusedWhileTheAccountIsLocked() {
        user.setLockedUntil(Instant.now().plus(10, ChronoUnit.MINUTES));

        assertThatThrownBy(() -> authService.login("analyst-1", PASSWORD, CLIENT))
                .isInstanceOf(TooManyAttemptsException.class);

        verify(refreshTokenService, never()).issue(any());
    }

    @Test
    void anExpiredLockNoLongerBlocksAValidLogin() {
        user.setLockedUntil(Instant.now().minus(1, ChronoUnit.MINUTES));

        AuthenticatedSession session = authService.login("analyst-1", PASSWORD, CLIENT);

        assertThat(session.response().token()).isNotBlank();
        assertThat(user.getLockedUntil()).isNull();
    }

    @Test
    void aSuccessfulLoginClearsAPartialFailureStreak() {
        assertThatThrownBy(() -> authService.login("analyst-1", "wrong", CLIENT))
                .isInstanceOf(InvalidCredentialsException.class);
        assertThat(user.getFailedLoginAttempts()).isEqualTo(1);

        authService.login("analyst-1", PASSWORD, CLIENT);

        assertThat(user.getFailedLoginAttempts()).isZero();
    }

    @Test
    void aDisabledAccountCannotLogInWithTheRightPassword() {
        user.setEnabled(false);

        assertThatThrownBy(() -> authService.login("analyst-1", PASSWORD, CLIENT))
                .isInstanceOf(InvalidCredentialsException.class);

        verify(refreshTokenService, never()).issue(any());
    }

    @Test
    void anUnknownUsernameFailsWithTheSameMessageAsAWrongPassword() {
        given(userRepository.findByUsername("ghost")).willReturn(Optional.empty());

        assertThatThrownBy(() -> authService.login("ghost", PASSWORD, CLIENT))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Kredenciale te pasakta.");

        assertThatThrownBy(() -> authService.login("analyst-1", "wrong", CLIENT))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessage("Kredenciale te pasakta.");
    }

    @Test
    void tooManyFailuresFromOneClientAreThrottledAcrossUsernames() {
        LoginAttemptService tightLimit = new LoginAttemptService(2, 5);
        AuthService throttled = new AuthService(userRepository, passwordEncoder,
                new JwtService(SECRET, 15), refreshTokenService, tightLimit,
                new LoginStateService(userRepository, 100, 15));

        given(userRepository.findByUsername("ghost")).willReturn(Optional.empty());

        assertThatThrownBy(() -> throttled.login("ghost", "x", CLIENT))
                .isInstanceOf(InvalidCredentialsException.class);
        assertThatThrownBy(() -> throttled.login("ghost", "x", CLIENT))
                .isInstanceOf(InvalidCredentialsException.class);

        assertThatThrownBy(() -> throttled.login("analyst-1", PASSWORD, CLIENT))
                .isInstanceOf(TooManyAttemptsException.class);
    }

    @Test
    void changingThePasswordRevokesEverySession() {
        authService.changePassword("analyst-1",
                new ChangePasswordRequest(PASSWORD, "brand-new-pass-9", "brand-new-pass-9"));

        assertThat(passwordEncoder.matches("brand-new-pass-9", user.getPasswordHash())).isTrue();
        verify(refreshTokenService).revokeAllFor(user);
    }

    @Test
    void changingThePasswordRequiresTheCurrentOne() {
        assertThatThrownBy(() -> authService.changePassword("analyst-1",
                new ChangePasswordRequest("wrong", "brand-new-pass-9", "brand-new-pass-9")))
                .isInstanceOf(InvalidCredentialsException.class);

        verify(refreshTokenService, never()).revokeAllFor(any());
    }

    @Test
    void aMismatchedConfirmationIsRejected() {
        assertThatThrownBy(() -> authService.changePassword("analyst-1",
                new ChangePasswordRequest(PASSWORD, "brand-new-pass-9", "something-else-9")))
                .isInstanceOf(InvalidRequestException.class);

        verify(refreshTokenService, never()).revokeAllFor(any());
    }

    @Test
    void reusingTheCurrentPasswordAsTheNewOneIsRejected() {
        assertThatThrownBy(() -> authService.changePassword("analyst-1",
                new ChangePasswordRequest(PASSWORD, PASSWORD, PASSWORD)))
                .isInstanceOf(InvalidRequestException.class);

        verify(refreshTokenService, never()).revokeAllFor(any());
    }

    @Test
    void aTokenMintedRightAfterARevocationSurvivesTheRevocationCutoff() {
        Instant cutoff = Instant.now().truncatedTo(ChronoUnit.SECONDS).plusSeconds(1);
        user.setTokensValidFrom(cutoff);

        AuthenticatedSession session = authService.login("analyst-1", PASSWORD, CLIENT);
        Instant issuedAt = jwtService.parse(session.response().token())
                .orElseThrow()
                .getIssuedAt()
                .toInstant();

        assertThat(issuedAt.isBefore(cutoff)).isFalse();
    }

    @Test
    void twoTokensMintedInTheSameSecondAreStillDistinct() {
        String first = authService.login("analyst-1", PASSWORD, CLIENT).response().token();
        String second = authService.login("analyst-1", PASSWORD, CLIENT).response().token();

        assertThat(first).isNotEqualTo(second);
    }

    @Test
    void refreshingRotatesTheStoredTokenAndMintsANewAccessToken() {
        given(refreshTokenService.rotate("old-token"))
                .willReturn(new RefreshTokenService.Rotation(user, "new-token"));

        AuthenticatedSession session = authService.refresh("old-token");

        assertThat(session.refreshToken()).isEqualTo("new-token");
        assertThat(session.response().token()).isNotBlank();
        assertThat(session.response().role()).isEqualTo("ANALYST");
    }
}
