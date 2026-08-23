package com.diploma.idsml.service;

import com.diploma.idsml.dto.ExplanationResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.Explanation;
import com.diploma.idsml.entity.ExplanationRating;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AlarmRepository;
import com.diploma.idsml.repository.ExplanationRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class ExplanationService {

    private final ExplanationRepository explanationRepository;
    private final AlarmRepository alarmRepository;

    public ExplanationService(ExplanationRepository explanationRepository,
                               AlarmRepository alarmRepository) {
        this.explanationRepository = explanationRepository;
        this.alarmRepository = alarmRepository;
    }

    public List<ExplanationResponse> getByAlarmId(UUID alarmId) {
        return explanationRepository.findByAlarmIdOrderByGeneratedAtAsc(alarmId).stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    @Transactional
    public ExplanationResponse save(UUID alarmId, String explanationText,
                                     String llmModel, String llmPromptVersion,
                                     Double generationLatencyMs) {
        Alarm alarm = alarmRepository.findById(alarmId)
                .orElseThrow(() -> new ResourceNotFoundException("Alarm s'u gjet: " + alarmId));

        Explanation explanation = Explanation.builder()
                .alarm(alarm)
                .explanationText(explanationText)
                .llmModel(llmModel)
                .llmPromptVersion(llmPromptVersion)
                .generationLatencyMs(generationLatencyMs)
                .build();

        return toResponse(explanationRepository.save(explanation));
    }

    @Transactional
    public ExplanationResponse rate(UUID explanationId, ExplanationRating rating) {
        Explanation explanation = explanationRepository.findById(explanationId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Shpjegim s'u gjet: " + explanationId));

        explanation.setRating(rating);
        explanation.setRatedAt(Instant.now());

        return toResponse(explanationRepository.save(explanation));
    }

    private ExplanationResponse toResponse(Explanation explanation) {
        return new ExplanationResponse(
                explanation.getId(),
                explanation.getAlarm().getId(),
                explanation.getExplanationText(),
                explanation.getLlmModel(),
                explanation.getLlmPromptVersion(),
                explanation.getGeneratedAt(),
                explanation.getRating(),
                explanation.getRatedAt(),
                explanation.getGenerationLatencyMs()
        );
    }
}
