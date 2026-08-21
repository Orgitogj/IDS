package com.diploma.idsml.service;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AlarmRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class AlarmService {

    private final AlarmRepository alarmRepository;

    public AlarmService(AlarmRepository alarmRepository) {
        this.alarmRepository = alarmRepository;
    }

    public List<AlarmResponse> getAll() {
        return alarmRepository.findAll().stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    public List<AlarmResponse> getByStatus(AlarmStatus status) {
        return alarmRepository.findByStatus(status).stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    public AlarmResponse getById(UUID id) {
        return toResponse(findEntity(id));
    }

    @Transactional
    public AlarmResponse updateStatus(UUID id, AlarmStatus newStatus) {
        Alarm alarm = findEntity(id);
        alarm.setStatus(newStatus);

        if (newStatus == AlarmStatus.ACKNOWLEDGED && alarm.getAcknowledgedAt() == null) {
            alarm.setAcknowledgedAt(Instant.now());
        }
        if ((newStatus == AlarmStatus.RESOLVED || newStatus == AlarmStatus.FALSE_POSITIVE)
                && alarm.getResolvedAt() == null) {
            alarm.setResolvedAt(Instant.now());
        }

        return toResponse(alarmRepository.save(alarm));
    }

    private Alarm findEntity(UUID id) {
        return alarmRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Alarm s'u gjet: " + id));
    }

    private AlarmResponse toResponse(Alarm alarm) {
        return new AlarmResponse(
                alarm.getId(),
                alarm.getNetworkFlow().getId(),
                alarm.getSeverity(),
                alarm.getStatus(),
                alarm.getCreatedAt(),
                alarm.getAcknowledgedAt(),
                alarm.getResolvedAt()
        );
    }
}
