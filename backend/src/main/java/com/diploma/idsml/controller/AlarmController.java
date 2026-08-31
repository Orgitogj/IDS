package com.diploma.idsml.controller;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.dto.AlarmStatsResponse;
import com.diploma.idsml.dto.AlarmStatusUpdateRequest;
import com.diploma.idsml.dto.AlarmGroupResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.service.AlarmService;
import jakarta.validation.Valid;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/alarms")
public class AlarmController {

    private static final int MAX_PAGE_SIZE = 200;

    private final AlarmService alarmService;

    public AlarmController(AlarmService alarmService) {
        this.alarmService = alarmService;
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public PageResponse<AlarmResponse> search(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size,
            @RequestParam(required = false) AlarmSeverity severity,
            @RequestParam(required = false) AlarmStatus status,
            @RequestParam(required = false) String search) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        return alarmService.search(
                severity,
                status,
                search,
                PageRequest.of(safePage, safeSize, Sort.by(Sort.Direction.DESC, "createdAt"))
        );
    }

    @GetMapping("/stats")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public AlarmStatsResponse getStats() {
        return alarmService.getStats();
    }

    @GetMapping("/incidents")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public List<AlarmGroupResponse> getIncidents(
            @RequestParam(defaultValue = "50") int limit) {
        return alarmService.getIncidents(Math.min(Math.max(limit, 1), MAX_PAGE_SIZE));
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public AlarmResponse getById(@PathVariable UUID id) {
        return alarmService.getById(id);
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public AlarmResponse updateStatus(@PathVariable UUID id,
                                       @Valid @RequestBody AlarmStatusUpdateRequest request,
                                       Authentication authentication) {
        return alarmService.updateStatus(id, request.status(), authentication.getName());
    }
}
