package com.diploma.idsml.controller;

import com.diploma.idsml.dto.ExplanationCreateRequest;
import com.diploma.idsml.dto.ExplanationRatingRequest;
import com.diploma.idsml.dto.ExplanationResponse;
import com.diploma.idsml.service.ExplanationService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/alarms/{alarmId}/explanations")
public class ExplanationController {

    private final ExplanationService explanationService;

    public ExplanationController(ExplanationService explanationService) {
        this.explanationService = explanationService;
    }

    @PostMapping
    @PreAuthorize("hasAnyRole('SERVICE','ADMIN')")
    public ResponseEntity<ExplanationResponse> create(@PathVariable UUID alarmId,
                                                      @Valid @RequestBody ExplanationCreateRequest request) {
        ExplanationResponse response = explanationService.save(
                alarmId,
                request.explanationText(),
                request.llmModel(),
                request.llmPromptVersion(),
                request.generationLatencyMs()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public List<ExplanationResponse> getByAlarmId(@PathVariable UUID alarmId) {
        return explanationService.getByAlarmId(alarmId);
    }

    @PatchMapping("/{explanationId}/rating")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public ExplanationResponse rate(@PathVariable UUID alarmId,
                                    @PathVariable UUID explanationId,
                                    @Valid @RequestBody ExplanationRatingRequest request) {
        return explanationService.rate(explanationId, request.rating());
    }
}
