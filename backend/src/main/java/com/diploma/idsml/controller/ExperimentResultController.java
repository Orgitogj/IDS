package com.diploma.idsml.controller;

import com.diploma.idsml.dto.ExperimentResultCreateRequest;
import com.diploma.idsml.dto.ExperimentResultResponse;
import com.diploma.idsml.service.ExperimentResultService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/experiments")
public class ExperimentResultController {

    private final ExperimentResultService experimentResultService;

    public ExperimentResultController(ExperimentResultService experimentResultService) {
        this.experimentResultService = experimentResultService;
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public List<ExperimentResultResponse> getAll(@RequestParam(required = false) UUID modelId) {
        if (modelId != null) {
            return experimentResultService.getByModelId(modelId);
        }
        return experimentResultService.getAll();
    }

    @PostMapping
    @PreAuthorize("hasAnyRole('SERVICE','ADMIN')")
    public ResponseEntity<ExperimentResultResponse> create(@Valid @RequestBody ExperimentResultCreateRequest request) {
        ExperimentResultResponse response = experimentResultService.recordResult(
                request.mlModelId(),
                request.testedOnDataset(),
                request.featureSetUsed(),
                request.accuracy(),
                request.precisionScore(),
                request.recall(),
                request.f1Score(),
                request.avgLatencyMs(),
                request.sampleSize(),
                request.notes()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public ExperimentResultResponse getById(@PathVariable UUID id) {
        return experimentResultService.getById(id);
    }
}