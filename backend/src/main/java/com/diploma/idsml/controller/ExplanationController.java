package com.diploma.idsml.controller;

import com.diploma.idsml.dto.ExplanationCreateRequest;
import com.diploma.idsml.dto.ExplanationResponse;
import com.diploma.idsml.service.ExplanationService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/alarms/{alarmId}/explanation")
public class ExplanationController {

    private final ExplanationService explanationService;

    public ExplanationController(ExplanationService explanationService) {
        this.explanationService = explanationService;
    }

    @PostMapping
    public ResponseEntity<ExplanationResponse> create(@PathVariable UUID alarmId,
                                                      @Valid @RequestBody ExplanationCreateRequest request) {
        ExplanationResponse response = explanationService.save(
                alarmId,
                request.explanationText(),
                request.llmModel(),
                request.llmPromptVersion()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    public ExplanationResponse getByAlarmId(@PathVariable UUID alarmId) {
        return explanationService.getByAlarmId(alarmId);
    }
}