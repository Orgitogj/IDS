package com.diploma.idsml.service;

import com.diploma.idsml.dto.AnalystFeedbackResponse;
import com.diploma.idsml.dto.FeedbackStatsResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.AnalystFeedback;
import com.diploma.idsml.entity.NetworkFlow;
import com.diploma.idsml.repository.AnalystFeedbackRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class AnalystFeedbackService {

    private static final Logger log = LoggerFactory.getLogger(AnalystFeedbackService.class);

    public static final Set<AlarmStatus> RECORDABLE_VERDICTS =
            EnumSet.of(AlarmStatus.FALSE_POSITIVE, AlarmStatus.CONFIRMED);

    private final AnalystFeedbackRepository feedbackRepository;
    private final ObjectMapper objectMapper;

    public AnalystFeedbackService(AnalystFeedbackRepository feedbackRepository,
                                  ObjectMapper objectMapper) {
        this.feedbackRepository = feedbackRepository;
        this.objectMapper = objectMapper;
    }

    public static boolean isRecordable(AlarmStatus status) {
        return RECORDABLE_VERDICTS.contains(status);
    }

    @Transactional
    public void record(Alarm alarm, AlarmStatus verdict, String analystUsername) {
        if (!isRecordable(verdict)) {
            return;
        }
        if (feedbackRepository.existsByAlarmIdAndAnalystVerdict(alarm.getId(), verdict)) {
            return;
        }

        NetworkFlow flow = alarm.getNetworkFlow();

        AnalystFeedback feedback = AnalystFeedback.builder()
                .alarmId(alarm.getId())
                .networkFlowId(flow.getId())
                .incidentId(alarm.getIncident() != null ? alarm.getIncident().getId() : null)
                .originalPrediction(flow.getPredictedLabel())
                .originalAttackType(flow.getAttackType())
                .originalConfidence(flow.getPredictionConfidence())
                .originalAnomalyScore(flow.getAnomalyScore())
                .detectionMethod(flow.getDetectionMethod())
                .analystVerdict(verdict)
                .analystAttackType(verdict == AlarmStatus.CONFIRMED ? flow.getAttackType() : null)
                .analystUsername(analystUsername)
                .modelId(flow.getModelId())
                .modelName(flow.getModelName())
                .modelVersion(flow.getModelVersion())
                .featureVersion(flow.getFeatureVersion())
                .featureVector(flow.getFeatureVector())
                .groundTruthLabel(flow.getGroundTruthAttackType())
                .build();

        feedbackRepository.save(feedback);
        log.debug("Feedback u ruajt per alarmin {} ({} nga {})",
                alarm.getId(), verdict, analystUsername);
    }

    public PageResponse<AnalystFeedbackResponse> search(Pageable pageable) {
        Page<AnalystFeedback> page = feedbackRepository.findAllByOrderByCreatedAtDesc(pageable);

        return new PageResponse<>(
                page.getContent().stream().map(this::toResponse).collect(Collectors.toList()),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages()
        );
    }

    public FeedbackStatsResponse getStats() {
        Map<String, Long> verdictCounts = new LinkedHashMap<>();
        for (AlarmStatus verdict : RECORDABLE_VERDICTS) {
            verdictCounts.put(verdict.name(), 0L);
        }
        for (Object[] row : feedbackRepository.countGroupedByVerdict()) {
            verdictCounts.put(((AlarmStatus) row[0]).name(), (Long) row[1]);
        }

        long falsePositives = verdictCounts.getOrDefault(AlarmStatus.FALSE_POSITIVE.name(), 0L);
        long total = verdictCounts.values().stream().mapToLong(Long::longValue).sum();

        Map<String, Map<String, Long>> byModel = new LinkedHashMap<>();
        for (Object[] row : feedbackRepository.countGroupedByModelAndVerdict()) {
            String modelName = row[0] != null ? (String) row[0] : "(unrecorded)";
            byModel.computeIfAbsent(modelName, key -> new LinkedHashMap<>())
                    .put(((AlarmStatus) row[1]).name(), (Long) row[2]);
        }

        return new FeedbackStatsResponse(
                total,
                verdictCounts,
                total == 0 ? 0.0 : (double) falsePositives / total,
                byModel
        );
    }

    public String exportAsJsonl() {
        List<AnalystFeedback> all = feedbackRepository.findAll();
        StringBuilder builder = new StringBuilder();

        for (AnalystFeedback feedback : all) {
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("feedback_id", feedback.getId().toString());
            record.put("alarm_id", feedback.getAlarmId().toString());
            record.put("network_flow_id", feedback.getNetworkFlowId().toString());
            record.put("original_prediction", feedback.getOriginalPrediction() != null
                    ? feedback.getOriginalPrediction().name() : null);
            record.put("original_attack_type", feedback.getOriginalAttackType());
            record.put("original_confidence", feedback.getOriginalConfidence());
            record.put("original_anomaly_score", feedback.getOriginalAnomalyScore());
            record.put("detection_method", feedback.getDetectionMethod() != null
                    ? feedback.getDetectionMethod().name() : null);
            record.put("analyst_verdict", feedback.getAnalystVerdict().name());
            record.put("analyst_attack_type", feedback.getAnalystAttackType());
            record.put("ground_truth_label", feedback.getGroundTruthLabel());
            record.put("model_id", feedback.getModelId() != null
                    ? feedback.getModelId().toString() : null);
            record.put("model_name", feedback.getModelName());
            record.put("model_version", feedback.getModelVersion());
            record.put("feature_version", feedback.getFeatureVersion());
            record.put("created_at", feedback.getCreatedAt().toString());
            record.put("features", feedback.getFeatureVector());

            try {
                builder.append(objectMapper.writeValueAsString(record)).append('\n');
            } catch (JsonProcessingException ex) {
                log.warn("Feedback {} s'u serializua dot: {}", feedback.getId(), ex.getMessage());
            }
        }

        return builder.toString();
    }

    private AnalystFeedbackResponse toResponse(AnalystFeedback feedback) {
        return new AnalystFeedbackResponse(
                feedback.getId(),
                feedback.getAlarmId(),
                feedback.getNetworkFlowId(),
                feedback.getIncidentId(),
                feedback.getOriginalPrediction(),
                feedback.getOriginalAttackType(),
                feedback.getOriginalConfidence(),
                feedback.getOriginalAnomalyScore(),
                feedback.getDetectionMethod(),
                feedback.getAnalystVerdict(),
                feedback.getAnalystAttackType(),
                feedback.getAnalystUsername(),
                feedback.getNotes(),
                feedback.getModelId(),
                feedback.getModelName(),
                feedback.getModelVersion(),
                feedback.getFeatureVersion(),
                feedback.getGroundTruthLabel(),
                feedback.getCreatedAt()
        );
    }
}
