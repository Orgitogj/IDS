package com.diploma.idsml.controller;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.dto.AlarmStatusUpdateRequest;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.service.AlarmService;
import jakarta.validation.Valid;
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

    private final AlarmService alarmService;

    public AlarmController(AlarmService alarmService) {
        this.alarmService = alarmService;
    }

    @GetMapping
    public List<AlarmResponse> getAll(@RequestParam(required = false) AlarmStatus status) {
        if (status != null) {
            return alarmService.getByStatus(status);
        }
        return alarmService.getAll();
    }

    @GetMapping("/{id}")
    public AlarmResponse getById(@PathVariable UUID id) {
        return alarmService.getById(id);
    }

    @PatchMapping("/{id}/status")
    public AlarmResponse updateStatus(@PathVariable UUID id,
                                       @Valid @RequestBody AlarmStatusUpdateRequest request) {
        return alarmService.updateStatus(id, request.status());
    }
}
