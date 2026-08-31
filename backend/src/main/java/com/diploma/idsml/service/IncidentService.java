package com.diploma.idsml.service;

import com.diploma.idsml.dto.IncidentResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.Incident;
import com.diploma.idsml.entity.NetworkFlow;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.IncidentRepository;
import jakarta.persistence.criteria.Predicate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class IncidentService {

    private static final String UNKNOWN_ATTACK_KEY = "UNKNOWN";

    private final IncidentRepository incidentRepository;
    private final Duration correlationWindow;

    public IncidentService(IncidentRepository incidentRepository,
                           @Value("${ids.correlation.window-seconds}") long windowSeconds) {
        this.incidentRepository = incidentRepository;
        this.correlationWindow = Duration.ofSeconds(windowSeconds);
    }

    public Duration getCorrelationWindow() {
        return correlationWindow;
    }

    public static String correlationKey(NetworkFlow flow) {
        String source = flow.getSourceIp() != null ? flow.getSourceIp() : "unknown-source";
        String attack = flow.getAttackType() != null ? flow.getAttackType() : UNKNOWN_ATTACK_KEY;
        return source + "|" + attack;
    }

    @Transactional
    public Incident correlate(Alarm alarm, NetworkFlow flow) {
        String key = correlationKey(flow);
        incidentRepository.lockCorrelationKey(key);

        Instant observedAt = flow.getFlowTimestamp() != null
                ? flow.getFlowTimestamp()
                : alarm.getCreatedAt();
        Instant notBefore = observedAt.minus(correlationWindow);

        Incident incident = incidentRepository.findOpenByCorrelationKey(key, notBefore)
                .stream()
                .findFirst()
                .orElseGet(() -> newIncident(key, flow, observedAt, alarm.getSeverity()));

        incident.setFlowCount(incident.getFlowCount() + 1);
        incident.setAlarmCount(incident.getAlarmCount() + 1);
        incident.trackDestination(flow.getDestinationIp());

        if (observedAt.isBefore(incident.getFirstSeen())) {
            incident.setFirstSeen(observedAt);
        }
        if (observedAt.isAfter(incident.getLastSeen())) {
            incident.setLastSeen(observedAt);
        }
        if (isMoreSevere(alarm.getSeverity(), incident.getSeverity())) {
            incident.setSeverity(alarm.getSeverity());
        }
        incident.setUpdatedAt(Instant.now());

        Incident saved = incidentRepository.save(incident);
        alarm.setIncident(saved);
        return saved;
    }

    private Incident newIncident(String key, NetworkFlow flow, Instant observedAt,
                                 AlarmSeverity severity) {
        return Incident.builder()
                .correlationKey(key)
                .sourceIp(flow.getSourceIp())
                .attackType(flow.getAttackType())
                .detectionMethod(flow.getDetectionMethod())
                .destinationIps(new ArrayList<>())
                .firstSeen(observedAt)
                .lastSeen(observedAt)
                .severity(severity)
                .status(AlarmStatus.NEW)
                .build();
    }

    private boolean isMoreSevere(AlarmSeverity candidate, AlarmSeverity current) {
        if (candidate == null) {
            return false;
        }
        return current == null || candidate.ordinal() > current.ordinal();
    }

    public PageResponse<IncidentResponse> search(AlarmSeverity severity, AlarmStatus status,
                                                 String search, Pageable pageable) {
        Page<Incident> page = incidentRepository.findAll(buildFilter(severity, status, search),
                pageable);

        return new PageResponse<>(
                page.getContent().stream().map(this::toResponse).collect(Collectors.toList()),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages()
        );
    }

    private Specification<Incident> buildFilter(AlarmSeverity severity, AlarmStatus status,
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
                String pattern = "%" + search.toLowerCase() + "%";
                predicates.add(cb.or(
                        cb.like(cb.lower(root.get("sourceIp")), pattern),
                        cb.like(cb.lower(root.get("attackType")), pattern),
                        cb.like(cb.lower(root.get("correlationKey")), pattern)
                ));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    public IncidentResponse getById(UUID id) {
        return toResponse(findEntity(id));
    }

    @Transactional
    public IncidentResponse updateStatus(UUID id, AlarmStatus newStatus) {
        Incident incident = findEntity(id);
        incident.setStatus(newStatus);
        incident.setUpdatedAt(Instant.now());
        return toResponse(incidentRepository.save(incident));
    }

    private Incident findEntity(UUID id) {
        return incidentRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Incident s'u gjet: " + id));
    }

    public IncidentResponse toResponse(Incident incident) {
        long destinationCount = incident.isDestinationsTruncated()
                ? incidentRepository.countDistinctDestinations(incident.getId())
                : incident.getDestinationIps().size();

        return new IncidentResponse(
                incident.getId(),
                incident.getCorrelationKey(),
                incident.getSourceIp(),
                incident.getAttackType(),
                incident.getDetectionMethod(),
                List.copyOf(incident.getDestinationIps()),
                incident.isDestinationsTruncated(),
                destinationCount,
                incident.getFirstSeen(),
                incident.getLastSeen(),
                incident.getFlowCount(),
                incident.getAlarmCount(),
                incident.getSeverity(),
                incident.getStatus(),
                incident.getCreatedAt(),
                incident.getUpdatedAt()
        );
    }
}
