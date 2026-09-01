package com.diploma.idsml.controller;

import com.diploma.idsml.config.SecurityConfig;
import com.diploma.idsml.dto.DriftReportResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.DriftStatus;
import com.diploma.idsml.exception.GlobalExceptionHandler;
import com.diploma.idsml.security.JwtAuthenticationFilter;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.security.RestAccessDeniedHandler;
import com.diploma.idsml.security.RestAuthenticationEntryPoint;
import com.diploma.idsml.security.TokenAuthenticator;
import com.diploma.idsml.security.JwtService;
import com.diploma.idsml.service.DriftReportService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static com.diploma.idsml.support.AuthTestSupport.stubRoleNamedUsers;
import static com.diploma.idsml.support.AuthTestSupport.usernameFor;

@WebMvcTest(DriftReportController.class)
@Import({SecurityConfig.class, JwtAuthenticationFilter.class, JwtService.class,
        TokenAuthenticator.class, RestAuthenticationEntryPoint.class,
        RestAccessDeniedHandler.class, GlobalExceptionHandler.class})
@TestPropertySource(properties = {
        "ids.security.jwt-secret=ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=",
        "ids.security.jwt-expiration-minutes=60"
})
class DriftReportControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private DriftReportService driftReportService;

    @MockBean
    private AppUserRepository userRepository;

    private Map<String, Object> payload;

    @BeforeEach
    void setUp() {
        stubRoleNamedUsers(userRepository);
        payload = new LinkedHashMap<>();
        payload.put("status", "WARNING");
        payload.put("featureVersion", "cicids2017-78-v1");
        payload.put("observedFlows", 1000L);
        payload.put("acceptedFlows", 980L);
        payload.put("rejectedFlows", 20L);
        payload.put("sampleSize", 980);
        payload.put("invalidRate", 0.02);
        payload.put("driftedFeatureCount", 6);
        payload.put("driftedFraction", 0.12);
        payload.put("calibrationWindow", 1000);
        payload.put("reasons", List.of("invalid-vector rate 2.0% above 1%"));
        payload.put("driftedFeatures", List.of("Flow Duration", "Flow IAT Mean"));
        payload.put("features", Map.of("Flow Duration", Map.of("ks_statistic", 0.41)));
        payload.put("generatedAt", "2026-08-31T10:00:00Z");
    }

    private String token(String role) {
        return "Bearer " + jwtService.generateToken(usernameFor(role), role);
    }

    private DriftReportResponse response() {
        return new DriftReportResponse(
                UUID.randomUUID(), DriftStatus.WARNING, "cicids2017-78-v1",
                1000L, 980L, 20L, 980, 0.02, 6, 0.12, 1000,
                List.of("invalid-vector rate 2.0% above 1%"),
                List.of("Flow Duration", "Flow IAT Mean"),
                Map.of(), Instant.parse("2026-08-31T10:00:00Z"), Instant.now());
    }

    @Test
    void theServiceAccountCanPublishADriftReport() throws Exception {
        given(driftReportService.record(any())).willReturn(response());

        mockMvc.perform(post("/api/drift/reports")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("WARNING"))
                .andExpect(jsonPath("$.driftedFeatureCount").value(6));
    }

    @Test
    void ananalystCannotPublishADriftReport() throws Exception {
        mockMvc.perform(post("/api/drift/reports")
                        .header("Authorization", token("ANALYST"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isForbidden());

        verifyNoInteractions(driftReportService);
    }

    @Test
    void anonymousCannotPublishADriftReport() throws Exception {
        mockMvc.perform(post("/api/drift/reports")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(driftReportService);
    }

    @Test
    void anUnknownDriftStatusIsRejected() throws Exception {
        payload.put("status", "MELTDOWN");

        mockMvc.perform(post("/api/drift/reports")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void aReportMissingRequiredFieldsIsRejected() throws Exception {
        payload.remove("status");
        payload.remove("invalidRate");

        mockMvc.perform(post("/api/drift/reports")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(driftReportService);
    }

    @ParameterizedTest
    @ValueSource(strings = {"ANALYST", "ADMIN"})
    void analystsAndAdminsCanReadTheCurrentStatus(String role) throws Exception {
        given(driftReportService.getLatest()).willReturn(response());

        mockMvc.perform(get("/api/drift/status").header("Authorization", token(role)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("WARNING"))
                .andExpect(jsonPath("$.driftedFeatures[0]").value("Flow Duration"));
    }

    @Test
    void noDriftReportYetIsNoContentRatherThanAnError() throws Exception {
        given(driftReportService.getLatest()).willReturn(null);

        mockMvc.perform(get("/api/drift/status").header("Authorization", token("ANALYST")))
                .andExpect(status().isNoContent());
    }

    @Test
    void theServiceAccountCannotReadTheDashboardStatus() throws Exception {
        mockMvc.perform(get("/api/drift/status").header("Authorization", token("SERVICE")))
                .andExpect(status().isForbidden());
    }

    @Test
    void historyIsPagedForAnalysts() throws Exception {
        given(driftReportService.history(any()))
                .willReturn(new PageResponse<>(List.of(response()), 0, 50, 1, 1));

        mockMvc.perform(get("/api/drift/history").header("Authorization", token("ANALYST")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.content[0].status").value("WARNING"));
    }

    @Test
    void anonymousCannotReadDriftHistory() throws Exception {
        mockMvc.perform(get("/api/drift/history"))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(driftReportService);
    }
}
