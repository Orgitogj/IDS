package com.diploma.idsml.controller;

import com.diploma.idsml.dto.AnalystFeedbackResponse;
import com.diploma.idsml.dto.FeedbackStatsResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.service.AnalystFeedbackService;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/feedback")
public class AnalystFeedbackController {

    private static final int MAX_PAGE_SIZE = 200;

    private final AnalystFeedbackService feedbackService;

    public AnalystFeedbackController(AnalystFeedbackService feedbackService) {
        this.feedbackService = feedbackService;
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public PageResponse<AnalystFeedbackResponse> search(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        return feedbackService.search(PageRequest.of(safePage, safeSize));
    }

    @GetMapping("/stats")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public FeedbackStatsResponse getStats() {
        return feedbackService.getStats();
    }

    @GetMapping("/export")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<String> export() {
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"analyst_feedback.jsonl\"")
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(feedbackService.exportAsJsonl());
    }
}
