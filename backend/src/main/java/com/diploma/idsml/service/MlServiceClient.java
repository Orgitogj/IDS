package com.diploma.idsml.service;

import com.diploma.idsml.exception.MlServiceUnavailableException;
import com.diploma.idsml.exception.ModelActivationException;
import com.diploma.idsml.security.JwtService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.util.UUID;

@Component
public class MlServiceClient {

    static final String SERVICE_SUBJECT = "idsml-backend";
    private static final int CONNECT_TIMEOUT_MS = 3_000;
    private static final int READ_TIMEOUT_MS = 30_000;

    private final RestClient restClient;
    private final JwtService jwtService;
    private final ObjectMapper objectMapper;

    @Autowired
    public MlServiceClient(@Value("${ids.ml-service.base-url}") String baseUrl,
                           JwtService jwtService,
                           ObjectMapper objectMapper) {
        this(RestClient.builder().baseUrl(baseUrl).requestFactory(requestFactory()),
                jwtService, objectMapper);
    }

    MlServiceClient(RestClient.Builder builder, JwtService jwtService, ObjectMapper objectMapper) {
        this.restClient = builder.build();
        this.jwtService = jwtService;
        this.objectMapper = objectMapper;
    }

    public void activate(UUID modelId) {
        String token = jwtService.generateToken(SERVICE_SUBJECT, "SERVICE");
        try {
            restClient.post()
                    .uri("/api/models/{id}/activate", modelId)
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                    .retrieve()
                    .toBodilessEntity();
        } catch (HttpClientErrorException ex) {
            throw new ModelActivationException(detailOf(ex));
        } catch (RestClientException ex) {
            throw new MlServiceUnavailableException(
                    "ml-service s'u arrit ose deshtoi; modeli nuk u aktivizua.");
        }
    }

    private String detailOf(HttpClientErrorException ex) {
        try {
            JsonNode detail = objectMapper.readTree(ex.getResponseBodyAsString()).get("detail");
            if (detail != null && detail.isTextual()) {
                return detail.asText();
            }
        } catch (JsonProcessingException ignored) {
        }
        return "ml-service e refuzoi modelin (HTTP " + ex.getStatusCode().value() + ").";
    }

    private static SimpleClientHttpRequestFactory requestFactory() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(CONNECT_TIMEOUT_MS);
        factory.setReadTimeout(READ_TIMEOUT_MS);
        return factory;
    }
}
