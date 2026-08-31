package com.diploma.idsml.controller;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.dto.IncidentResponse;
import com.diploma.idsml.dto.IncidentStatusUpdateRequest;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.service.AlarmService;
import com.diploma.idsml.service.IncidentService;
import jakarta.validation.Valid;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.prepost.PreAuthorize;
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
@RequestMapping("/api/incidents")
public class IncidentController {

    private static final int MAX_PAGE_SIZE = 200;

    private final IncidentService incidentService;
    private final AlarmService alarmService;

    public IncidentController(IncidentService incidentService, AlarmService alarmService) {
        this.incidentService = incidentService;
        this.alarmService = alarmService;
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public PageResponse<IncidentResponse> search(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size,
            @RequestParam(required = false) AlarmSeverity severity,
            @RequestParam(required = false) AlarmStatus status,
            @RequestParam(required = false) String search) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        return incidentService.search(
                severity,
                status,
                search,
                PageRequest.of(safePage, safeSize, Sort.by(Sort.Direction.DESC, "lastSeen"))
        );
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public IncidentResponse getById(@PathVariable UUID id) {
        return incidentService.getById(id);
    }

    @GetMapping("/{id}/alarms")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public List<AlarmResponse> getAlarms(@PathVariable UUID id) {
        return alarmService.getByIncidentId(id);
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAnyRole('ANALYST','ADMIN')")
    public IncidentResponse updateStatus(@PathVariable UUID id,
                                          @Valid @RequestBody IncidentStatusUpdateRequest request) {
        return incidentService.updateStatus(id, request.status());
    }
}
