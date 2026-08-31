package com.diploma.idsml.controller;

import com.diploma.idsml.dto.MLModelCreateRequest;
import com.diploma.idsml.dto.MLModelResponse;
import com.diploma.idsml.service.MLModelService;
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
@RequestMapping("/api/models")
public class MLModelController {

    private final MLModelService mlModelService;

    public MLModelController(MLModelService mlModelService) {
        this.mlModelService = mlModelService;
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public List<MLModelResponse> getAll() {
        return mlModelService.getAll();
    }

    @GetMapping("/active")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN','SERVICE')")
    public MLModelResponse getActive() {
        return mlModelService.getActive();
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN','SERVICE')")
    public MLModelResponse getById(@PathVariable UUID id) {
        return mlModelService.getById(id);
    }

    @PostMapping
    @PreAuthorize("hasAnyRole('SERVICE','ADMIN')")
    public ResponseEntity<MLModelResponse> create(@Valid @RequestBody MLModelCreateRequest request) {
        MLModelResponse response = mlModelService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PatchMapping("/{id}/activate")
    @PreAuthorize("hasRole('ADMIN')")
    public MLModelResponse setActive(@PathVariable UUID id) {
        return mlModelService.setActive(id);
    }
}