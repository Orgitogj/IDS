package com.diploma.idsml.service;

import com.diploma.idsml.dto.AlarmResponse;
import com.diploma.idsml.dto.NetworkFlowIngestRequest;
import com.diploma.idsml.dto.NetworkFlowResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.entity.NetworkFlow;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AlarmRepository;
import com.diploma.idsml.repository.NetworkFlowRepository;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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

    public List<NetworkFlowResponse> getAll() {
        return networkFlowRepository.findAll().stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
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