package com.diploma.idsml.service;

import com.diploma.idsml.exception.MlServiceUnavailableException;
import com.diploma.idsml.exception.ModelActivationException;
import com.diploma.idsml.security.JwtService;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class MlServiceClientTest {

    private static final String SECRET =
            "ZGV2LW9ubHktc2VjcmV0LWNoYW5nZS1tZS1pbi1wcm9kdWN0aW9uLTI1Ni1iaXQ=";

    private final JwtService jwtService = new JwtService(SECRET, 15);
    private final UUID modelId = UUID.randomUUID();

    private MockRestServiceServer server;
    private MlServiceClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://ml-service");
        server = MockRestServiceServer.bindTo(builder).build();
        client = new MlServiceClient(builder, jwtService, new ObjectMapper());
    }

    private String activateUrl() {
        return "http://ml-service/api/models/" + modelId + "/activate";
    }

    @Test
    void activationIsSentToTheMlServiceWithAServiceToken() {
        server.expect(requestTo(activateUrl()))
                .andExpect(method(HttpMethod.POST))
                .andExpect(request -> {
                    String header = request.getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
                    assertThat(header).startsWith("Bearer ");
                    Claims claims = jwtService.parse(header.substring("Bearer ".length())).orElseThrow();
                    assertThat(claims.get("role", String.class)).isEqualTo("SERVICE");
                })
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        client.activate(modelId);

        server.verify();
    }

    @Test
    void aRefusedModelCarriesTheMlServiceReason() {
        server.expect(requestTo(activateUrl()))
                .andRespond(withStatus(HttpStatus.UNPROCESSABLE_ENTITY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":\"Modeli 'mlp' (MLPClassifier) nuk mbeshtetet nga "
                                + "ml-service: lejohen vetem modele XGBoost.\"}"));

        assertThatThrownBy(() -> client.activate(modelId))
                .isInstanceOf(ModelActivationException.class)
                .hasMessageContaining("XGBoost");
    }

    @Test
    void anUnreachableMlServiceIsReportedAsUnavailable() {
        server.expect(requestTo(activateUrl()))
                .andRespond(withException(new IOException("Connection refused")));

        assertThatThrownBy(() -> client.activate(modelId))
                .isInstanceOf(MlServiceUnavailableException.class);
    }

    @Test
    void anMlServiceFailureIsReportedAsUnavailable() {
        server.expect(requestTo(activateUrl())).andRespond(withServerError());

        assertThatThrownBy(() -> client.activate(modelId))
                .isInstanceOf(MlServiceUnavailableException.class);
    }
}
