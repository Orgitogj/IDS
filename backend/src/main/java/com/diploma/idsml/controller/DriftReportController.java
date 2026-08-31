package com.diploma.idsml.controller;

import com.diploma.idsml.dto.DriftReportCreateRequest;
import com.diploma.idsml.dto.DriftReportResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.service.DriftReportService;
import jakarta.validation.Valid;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/drift")
public class DriftReportController {

    private static final int MAX_PAGE_SIZE = 200;

    private final DriftReportService driftReportService;

    public DriftReportController(DriftReportService driftReportService) {
        this.driftReportService = driftReportService;
    }

    @PostMapping("/reports")
    @PreAuthorize("hasAnyRole('SERVICE','ADMIN')")
    public ResponseEntity<DriftReportResponse> create(
            @Valid @RequestBody DriftReportCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(driftReportService.record(request));
    }

    @GetMapping("/status")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public ResponseEntity<DriftReportResponse> getStatus() {
        DriftReportResponse latest = driftReportService.getLatest();
        return latest == null ? ResponseEntity.noContent().build() : ResponseEntity.ok(latest);
    }

    @GetMapping("/history")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public PageResponse<DriftReportResponse> history(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        return driftReportService.history(PageRequest.of(safePage, safeSize));
    }
}
