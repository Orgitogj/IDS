package com.diploma.idsml.service;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.dto.AttackTypeCount;
import com.diploma.idsml.dto.FlowStatsResponse;
import com.diploma.idsml.dto.NetworkFlowIngestRequest;
import com.diploma.idsml.dto.NetworkFlowResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.entity.NetworkFlow;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AlarmRepository;
import com.diploma.idsml.repository.NetworkFlowRepository;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class NetworkFlowService {

    private final NetworkFlowRepository networkFlowRepository;
    private final AlarmRepository alarmRepository;
    private final SimpMessagingTemplate messagingTemplate;

    public NetworkFlowService(NetworkFlowRepository networkFlowRepository,
                              AlarmRepository alarmRepository,
                              SimpMessagingTemplate messagingTemplate) {
        this.networkFlowRepository = networkFlowRepository;
        this.alarmRepository = alarmRepository;
        this.messagingTemplate = messagingTemplate;
    }

    @Transactional
    public NetworkFlowResponse processFlowResult(NetworkFlowIngestRequest request) {
        NetworkFlow flow = NetworkFlow.builder()
                .datasetSource(request.datasetSource() != null
                        ? request.datasetSource()
                        : DatasetSource.LAB_LIVE)
                .sourceIp(request.sourceIp())
                .destinationIp(request.destinationIp())
                .sourcePort(request.sourcePort())
                .destinationPort(request.destinationPort())
                .protocol(request.protocol())
                .featureVector(request.featureVector())
                .label(FlowLabel.UNKNOWN)
                .attackType(request.attackType())
                .predictedLabel(request.predictedLabel())
                .predictionConfidence(request.predictionConfidence())
                .flowTimestamp(request.flowTimestamp())
                .build();

        flow = networkFlowRepository.save(flow);

        if (request.predictedLabel() == FlowLabel.ATTACK) {
            Alarm alarm = Alarm.builder()
                    .networkFlow(flow)
                    .severity(resolveSeverity(request.predictionConfidence()))
                    .status(AlarmStatus.NEW)
                    .build();
            alarm = alarmRepository.save(alarm);

            AlarmResponse alarmResponse = new AlarmResponse(
                    alarm.getId(),
                    flow.getId(),
                    alarm.getSeverity(),
                    alarm.getStatus(),
                    alarm.getCreatedAt(),
                    alarm.getAcknowledgedAt(),
                    alarm.getResolvedAt()
            );
            messagingTemplate.convertAndSend("/topic/alarms", alarmResponse);
        }

        return toResponse(flow);
    }

    public PageResponse<NetworkFlowResponse> search(FlowLabel predictedLabel, String search,
                                                    Pageable pageable) {
        Page<NetworkFlow> page = networkFlowRepository.findAll(
                buildFilter(predictedLabel, search), pageable);

        return new PageResponse<>(
                page.getContent().stream().map(this::toResponse).collect(Collectors.toList()),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages()
        );
    }

    public FlowStatsResponse getStats() {
        List<AttackTypeCount> counts = networkFlowRepository.countGroupedByAttackType().stream()
                .map(row -> new AttackTypeCount((String) row[0], (Long) row[1]))
                .collect(Collectors.toList());

        return new FlowStatsResponse(networkFlowRepository.count(), counts);
    }

    private Specification<NetworkFlow> buildFilter(FlowLabel predictedLabel, String search) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (predictedLabel != null) {
                predicates.add(cb.equal(root.get("predictedLabel"), predictedLabel));
            }

            if (search != null && !search.isBlank()) {
                String pattern = "%" + search.toLowerCase() + "%";
                predicates.add(cb.or(
                        cb.like(cb.lower(root.get("sourceIp")), pattern),
                        cb.like(cb.lower(root.get("destinationIp")), pattern),
                        cb.like(cb.lower(root.get("attackType")), pattern)
                ));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }

    public NetworkFlowResponse getById(UUID id) {
        NetworkFlow flow = networkFlowRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("NetworkFlow s'u gjet: " + id));
        return toResponse(flow);
    }

    private AlarmSeverity resolveSeverity(Double confidence) {
        if (confidence == null) {
            return AlarmSeverity.MEDIUM;
        }
        if (confidence >= 0.95) return AlarmSeverity.CRITICAL;
        if (confidence >= 0.85) return AlarmSeverity.HIGH;
        if (confidence >= 0.70) return AlarmSeverity.MEDIUM;
        return AlarmSeverity.LOW;
    }

    private NetworkFlowResponse toResponse(NetworkFlow flow) {
        return new NetworkFlowResponse(
                flow.getId(),
                flow.getDatasetSource(),
                flow.getSourceIp(),
                flow.getDestinationIp(),
                flow.getSourcePort(),
                flow.getDestinationPort(),
                flow.getProtocol(),
                flow.getFeatureVector(),
                flow.getLabel(),
                flow.getAttackType(),
                flow.getPredictedLabel(),
                flow.getPredictionConfidence(),
                flow.getFlowTimestamp(),
                flow.getCreatedAt()
        );
    }
}