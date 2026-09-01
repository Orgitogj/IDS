package com.diploma.idsml.controller;

import com.diploma.idsml.config.SecurityConfig;
import com.diploma.idsml.dto.NetworkFlowResponse;
import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.exception.GlobalExceptionHandler;
import com.diploma.idsml.exception.InvalidRequestException;
import com.diploma.idsml.security.JwtAuthenticationFilter;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.security.RestAccessDeniedHandler;
import com.diploma.idsml.security.RestAuthenticationEntryPoint;
import com.diploma.idsml.security.TokenAuthenticator;
import com.diploma.idsml.security.JwtService;
import com.diploma.idsml.service.NetworkFlowService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static com.diploma.idsml.support.AuthTestSupport.stubRoleNamedUsers;
import static com.diploma.idsml.support.AuthTestSupport.usernameFor;

@WebMvcTest(AlarmIngestController.class)
@Import({SecurityConfig.class, JwtAuthenticationFilter.class, JwtService.class,
        TokenAuthenticator.class, RestAuthenticationEntryPoint.class,
        RestAccessDeniedHandler.class, GlobalExceptionHandler.class})
@TestPropertySource(properties = {
        "ids.security.jwt-secret=ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=",
        "ids.security.jwt-expiration-minutes=60"
})
class AlarmIngestControllerTest {

    private static final UUID MODEL_ID = UUID.fromString("133f003c-baab-4e11-8b12-21f5f37e2896");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private NetworkFlowService networkFlowService;

    @MockBean
    private AppUserRepository userRepository;

    private Map<String, Object> payload;

    @BeforeEach
    void setUp() {
        stubRoleNamedUsers(userRepository);
        payload = new LinkedHashMap<>();
        payload.put("sourceIp", "10.0.0.5");
        payload.put("destinationIp", "10.0.0.100");
        payload.put("sourcePort", 44321);
        payload.put("destinationPort", 80);
        payload.put("protocol", "TCP");
        payload.put("featureVector", Map.of("Flow Duration", 1234.0));
        payload.put("predictedLabel", "ATTACK");
        payload.put("predictionConfidence", 0.97);
        payload.put("attackType", "PortScan");
        payload.put("modelId", MODEL_ID.toString());
        payload.put("modelName", "xgb-smote-top50features-v1");
        payload.put("modelVersion", "1.0");
        payload.put("featureVersion", "cicids2017-top50-v1");
        payload.put("detectionMethod", "SUPERVISED_ML");
        payload.put("flowTimestamp", "2026-08-30T12:00:00Z");
        payload.put("datasetSource", "LAB_LIVE");
    }

    private String token(String role) {
        return "Bearer " + jwtService.generateToken(usernameFor(role), role);
    }

    private String body() throws Exception {
        return objectMapper.writeValueAsString(payload);
    }

    private NetworkFlowResponse storedFlow() {
        return new NetworkFlowResponse(
                UUID.randomUUID(), DatasetSource.LAB_LIVE, "10.0.0.5", "10.0.0.100",
                44321, 80, "TCP", Map.of("Flow Duration", 1234.0), FlowLabel.UNKNOWN,
                "PortScan", null, FlowLabel.ATTACK, 0.97,
                MODEL_ID, "xgb-smote-top50features-v1", "1.0", "cicids2017-top50-v1",
                DetectionMethod.SUPERVISED_ML, null,
                Instant.parse("2026-08-30T12:00:00Z"), Instant.now());
    }

    @Test
    void serviceAccountCanIngestADetection() throws Exception {
        given(networkFlowService.processFlowResult(any())).willReturn(storedFlow());

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.modelName").value("xgb-smote-top50features-v1"))
                .andExpect(jsonPath("$.modelVersion").value("1.0"))
                .andExpect(jsonPath("$.featureVersion").value("cicids2017-top50-v1"))
                .andExpect(jsonPath("$.detectionMethod").value("SUPERVISED_ML"));
    }

    @Test
    void adminCanIngestADetection() throws Exception {
        given(networkFlowService.processFlowResult(any())).willReturn(storedFlow());

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("ADMIN"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isCreated());
    }

    @Test
    void analystCannotIngestADetection() throws Exception {
        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("ANALYST"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isForbidden());

        verifyNoInteractions(networkFlowService);
    }

    @Test
    void anonymousCannotIngestADetection() throws Exception {
        mockMvc.perform(post("/api/alarms/ingest")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(networkFlowService);
    }

    @Test
    void anInvalidTokenIsNotEnoughToIngest() throws Exception {
        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", "Bearer not-a-real-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(networkFlowService);
    }

    @Test
    void missingRequiredFieldsAreRejectedAsBadRequest() throws Exception {
        payload.remove("sourceIp");
        payload.remove("predictedLabel");

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(networkFlowService);
    }

    @Test
    void anUnknownDetectionMethodIsRejected() throws Exception {
        payload.put("detectionMethod", "TAROT_CARDS");

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void anUnknownModelIsRejectedAsBadRequestNotAServerError() throws Exception {
        given(networkFlowService.processFlowResult(any()))
                .willThrow(new InvalidRequestException("Modeli s'ekziston ne regjistrin e modeleve"));

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void aDetectionWithoutModelIdentityIsStillAccepted() throws Exception {
        Map<String, Object> legacy = new HashMap<>(payload);
        legacy.remove("modelId");
        legacy.remove("modelName");
        legacy.remove("modelVersion");
        legacy.remove("featureVersion");
        legacy.remove("detectionMethod");

        given(networkFlowService.processFlowResult(any())).willReturn(storedFlow());

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(legacy)))
                .andExpect(status().isCreated());
    }

    @Test
    void anAnomalyDetectionWithoutConfidenceIsAccepted() throws Exception {
        payload.put("predictedLabel", "UNKNOWN");
        payload.put("predictionConfidence", null);
        payload.put("attackType", null);
        payload.put("detectionMethod", "ANOMALY_DETECTION");
        payload.put("anomalyScore", 0.993);

        given(networkFlowService.processFlowResult(any())).willReturn(storedFlow());

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isCreated());
    }

    @Test
    void aDetectionWithNeitherConfidenceNorAnomalyScoreIsRejected() throws Exception {
        payload.put("predictionConfidence", null);
        payload.put("anomalyScore", null);

        given(networkFlowService.processFlowResult(any()))
                .willThrow(new InvalidRequestException(
                        "Nje detektim duhet te kete ose predictionConfidence ose anomalyScore."));

        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonIsRejected() throws Exception {
        mockMvc.perform(post("/api/alarms/ingest")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{not json"))
                .andExpect(status().isBadRequest());
    }
}
