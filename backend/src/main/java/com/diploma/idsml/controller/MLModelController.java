package com.diploma.idsml.controller;

import com.diploma.idsml.dto.MLModelCreateRequest;
import com.diploma.idsml.dto.MLModelResponse;
import com.diploma.idsml.service.MLModelService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
    public List<MLModelResponse> getAll() {
        return mlModelService.getAll();
    }

    @GetMapping("/{id}")
    public MLModelResponse getById(@PathVariable UUID id) {
        return mlModelService.getById(id);
    }

    @PostMapping
    public ResponseEntity<MLModelResponse> create(@Valid @RequestBody MLModelCreateRequest request) {
        MLModelResponse response = mlModelService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PatchMapping("/{id}/activate")
    public MLModelResponse setActive(@PathVariable UUID id) {
        return mlModelService.setActive(id);
    }
}