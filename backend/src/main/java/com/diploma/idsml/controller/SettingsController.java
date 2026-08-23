package com.diploma.idsml.controller;

import com.diploma.idsml.dto.SeverityThresholdsResponse;
import com.diploma.idsml.dto.SeverityThresholdsUpdateRequest;
import com.diploma.idsml.service.SeverityThresholdsService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/settings/thresholds")
public class SettingsController {

    private final SeverityThresholdsService severityThresholdsService;

    public SettingsController(SeverityThresholdsService severityThresholdsService) {
        this.severityThresholdsService = severityThresholdsService;
    }

    @GetMapping
    public SeverityThresholdsResponse get() {
        return severityThresholdsService.get();
    }

    @PutMapping
    public SeverityThresholdsResponse update(
            @Valid @RequestBody SeverityThresholdsUpdateRequest request) {
        return severityThresholdsService.update(
                request.criticalMin(),
                request.highMin(),
                request.mediumMin()
        );
    }
}
