package com.diploma.idsml.service;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.dto.AlarmStatsResponse;
import com.diploma.idsml.dto.HourlyCount;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AlarmRepository;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class AlarmService {

    private final AlarmRepository alarmRepository;

    public AlarmService(AlarmRepository alarmRepository) {
        this.alarmRepository = alarmRepository;
    }

    public PageResponse<AlarmResponse> search(AlarmSeverity severity, AlarmStatus status,
                                              String search, Pageable pageable) {
        Page<Alarm> page = alarmRepository.findAll(buildFilter(severity, status, search), pageable);

        return new PageResponse<>(
                page.getContent().stream().map(this::toResponse).collect(Collectors.toList()),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages()
        );
    }

    public AlarmStatsResponse getStats() {
        Map<String, Long> severityCounts = new LinkedHashMap<>();
        for (AlarmSeverity value : AlarmSeverity.values()) {
            severityCounts.put(value.name(), 0L);
        }
        for (Object[] row : alarmRepository.countGroupedBySeverity()) {
            severityCounts.put(((AlarmSeverity) row[0]).name(), (Long) row[1]);
        }

        Map<String, Long> statusCounts = new LinkedHashMap<>();
        for (AlarmStatus value : AlarmStatus.values()) {
            statusCounts.put(value.name(), 0L);
        }
        for (Object[] row : alarmRepository.countGroupedByStatus()) {
            statusCounts.put(((AlarmStatus) row[0]).name(), (Long) row[1]);
        }

        List<HourlyCount> hourlyCounts = alarmRepository.countGroupedByHour().stream()
                .map(row -> new HourlyCount((String) row[0], ((Number) row[1]).longValue()))
                .collect(Collectors.toList());

        return new AlarmStatsResponse(alarmRepository.count(), severityCounts, statusCounts,
                hourlyCounts);
    }

    private Specification<Alarm> buildFilter(AlarmSeverity severity, AlarmStatus status,
                                             String search) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (severity != null) {
                predicates.add(cb.equal(root.get("severity"), severity));
            }
            if (status != null) {
                predicates.add(cb.equal(root.get("status"), status));
            }
            if (search != null && !search.isBlank()) {
                predicates.add(cb.like(
                        cb.lower(root.get("id").as(String.class)),
                        "%" + search.toLowerCase() + "%"
                ));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
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
