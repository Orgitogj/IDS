package com.diploma.idsml.controller;

import com.diploma.idsml.config.SecurityConfig;
import com.diploma.idsml.dto.MLModelResponse;
import com.diploma.idsml.exception.GlobalExceptionHandler;
import com.diploma.idsml.exception.MlServiceUnavailableException;
import com.diploma.idsml.exception.ModelActivationException;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.security.JwtAuthenticationFilter;
import com.diploma.idsml.repository.AppUserRepository;
import com.diploma.idsml.security.RestAccessDeniedHandler;
import com.diploma.idsml.security.RestAuthenticationEntryPoint;
import com.diploma.idsml.security.TokenAuthenticator;
import com.diploma.idsml.security.JwtService;
import com.diploma.idsml.service.MLModelService;
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
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static com.diploma.idsml.support.AuthTestSupport.stubRoleNamedUsers;
import static com.diploma.idsml.support.AuthTestSupport.usernameFor;

@WebMvcTest(MLModelController.class)
@Import({SecurityConfig.class, JwtAuthenticationFilter.class, JwtService.class,
        TokenAuthenticator.class, RestAuthenticationEntryPoint.class,
        RestAccessDeniedHandler.class, GlobalExceptionHandler.class})
@TestPropertySource(properties = {
        "ids.security.jwt-secret=ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=",
        "ids.security.jwt-expiration-minutes=60"
})
class MLModelControllerTest {

    private static final UUID MODEL_ID = UUID.fromString("133f003c-baab-4e11-8b12-21f5f37e2896");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private MLModelService mlModelService;

    @MockBean
    private AppUserRepository userRepository;

    @BeforeEach
    void setUp() {
        stubRoleNamedUsers(userRepository);
    }

    private String token(String role) {
        return "Bearer " + jwtService.generateToken(usernameFor(role), role);
    }

    private MLModelResponse activeModel() {
        return new MLModelResponse(
                MODEL_ID, "XGBoost", "xgb-smote-top50features-v1", "1.0",
                "cicids2017-top50-v1", "CICIDS2017",
                "models/xgb_smote_top50features_v1.joblib", "{}",
                "top_50_features_by_importance", true,
                Instant.parse("2026-08-23T14:25:17Z"), Instant.parse("2026-08-23T14:25:17Z"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"ANALYST", "ADMIN", "SERVICE"})
    void everyAuthenticatedRoleCanReadTheActiveModel(String role) throws Exception {
        given(mlModelService.getActive()).willReturn(activeModel());

        mockMvc.perform(get("/api/models/active").header("Authorization", token(role)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("xgb-smote-top50features-v1"))
                .andExpect(jsonPath("$.version").value("1.0"))
                .andExpect(jsonPath("$.featureVersion").value("cicids2017-top50-v1"))
                .andExpect(jsonPath("$.artifactPath").value("models/xgb_smote_top50features_v1.joblib"));
    }

    @Test
    void anonymousCannotReadTheActiveModel() throws Exception {
        mockMvc.perform(get("/api/models/active"))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(mlModelService);
    }

    @Test
    void anAbsentActiveModelIsReportedAsNotFound() throws Exception {
        given(mlModelService.getActive())
                .willThrow(new ResourceNotFoundException("Asnje model aktiv"));

        mockMvc.perform(get("/api/models/active").header("Authorization", token("SERVICE")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void theServiceAccountCanResolveASingleModelById() throws Exception {
        given(mlModelService.getById(MODEL_ID)).willReturn(activeModel());

        mockMvc.perform(get("/api/models/" + MODEL_ID).header("Authorization", token("SERVICE")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(MODEL_ID.toString()));
    }

    @Test
    void theServiceAccountCannotListEveryModel() throws Exception {
        mockMvc.perform(get("/api/models").header("Authorization", token("SERVICE")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(mlModelService);
    }

    @Test
    void analystCanListModels() throws Exception {
        given(mlModelService.getAll()).willReturn(List.of(activeModel()));

        mockMvc.perform(get("/api/models").header("Authorization", token("ANALYST")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].featureVersion").value("cicids2017-top50-v1"));
    }

    @Test
    void onlyAdminCanActivateAModel() throws Exception {
        given(mlModelService.setActive(MODEL_ID)).willReturn(activeModel());

        mockMvc.perform(patch("/api/models/" + MODEL_ID + "/activate")
                        .header("Authorization", token("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.active").value(true));
    }

    @ParameterizedTest
    @ValueSource(strings = {"ANALYST", "SERVICE"})
    void nonAdminsCannotActivateAModel(String role) throws Exception {
        mockMvc.perform(patch("/api/models/" + MODEL_ID + "/activate")
                        .header("Authorization", token(role)))
                .andExpect(status().isForbidden());

        verifyNoInteractions(mlModelService);
    }

    @Test
    void anonymousCannotActivateAModel() throws Exception {
        mockMvc.perform(patch("/api/models/" + MODEL_ID + "/activate"))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(mlModelService);
    }

    @Test
    void aModelTheMlServiceCannotServeIsRejectedWithItsReason() throws Exception {
        given(mlModelService.setActive(MODEL_ID)).willThrow(new ModelActivationException(
                "Modeli 'mlp-smote-cicids2017-v1' (MLPClassifier) nuk mbështetet nga ml-service: "
                        + "lejohen vetëm modele XGBoost."));

        mockMvc.perform(patch("/api/models/" + MODEL_ID + "/activate")
                        .header("Authorization", token("ADMIN")))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.message").value(containsString("XGBoost")));
    }

    @Test
    void anUnreachableMlServiceBlocksActivation() throws Exception {
        given(mlModelService.setActive(MODEL_ID)).willThrow(new MlServiceUnavailableException(
                "ml-service nuk u arrit ose dështoi; modeli nuk u aktivizua."));

        mockMvc.perform(patch("/api/models/" + MODEL_ID + "/activate")
                        .header("Authorization", token("ADMIN")))
                .andExpect(status().isServiceUnavailable());
    }

    @Test
    void theServiceAccountCanRegisterAModelWithVersionMetadata() throws Exception {
        given(mlModelService.create(any())).willReturn(activeModel());

        Map<String, Object> body = Map.of(
                "algorithm", "XGBoost",
                "name", "xgb-smote-top50features-v2",
                "version", "2.0",
                "featureVersion", "cicids2017-top50-v1",
                "trainedOnDataset", "CICIDS2017",
                "artifactPath", "models/xgb_smote_top50features_v2.joblib",
                "trainedAt", "2026-08-30T12:00:00Z");

        mockMvc.perform(post("/api/models")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated());
    }

    @Test
    void registeringAModelWithoutRequiredFieldsIsRejected() throws Exception {
        Map<String, Object> body = Map.of("algorithm", "XGBoost");

        mockMvc.perform(post("/api/models")
                        .header("Authorization", token("SERVICE"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(mlModelService);
    }

    @Test
    void analystCannotRegisterAModel() throws Exception {
        Map<String, Object> body = Map.of(
                "algorithm", "XGBoost",
                "name", "sneaky",
                "trainedOnDataset", "CICIDS2017",
                "artifactPath", "models/sneaky.joblib",
                "trainedAt", "2026-08-30T12:00:00Z");

        mockMvc.perform(post("/api/models")
                        .header("Authorization", token("ANALYST"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isForbidden());

        verifyNoInteractions(mlModelService);
    }
}
