package com.diploma.idsml.service;

import com.diploma.idsml.dto.ExplanationResponse;
import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.Explanation;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.AlarmRepository;
import com.diploma.idsml.repository.ExplanationRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class ExplanationService {

    private final ExplanationRepository explanationRepository;
    private final AlarmRepository alarmRepository;

    public ExplanationService(ExplanationRepository explanationRepository,
                               AlarmRepository alarmRepository) {
        this.explanationRepository = explanationRepository;
        this.alarmRepository = alarmRepository;
    }

    public ExplanationResponse getByAlarmId(UUID alarmId) {
        Explanation explanation = explanationRepository.findByAlarmId(alarmId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Shpjegim s'u gjet per Alarm: " + alarmId));
        return toResponse(explanation);
    }

    @Transactional
    public ExplanationResponse save(UUID alarmId, String explanationText,
                                     String llmModel, String llmPromptVersion) {
        Alarm alarm = alarmRepository.findById(alarmId)
                .orElseThrow(() -> new ResourceNotFoundException("Alarm s'u gjet: " + alarmId));

        Explanation explanation = Explanation.builder()
                .alarm(alarm)
                .explanationText(explanationText)
                .llmModel(llmModel)
                .llmPromptVersion(llmPromptVersion)
                .build();

        return toResponse(explanationRepository.save(explanation));
    }

    private ExplanationResponse toResponse(Explanation explanation) {
        return new ExplanationResponse(
                explanation.getId(),
                explanation.getAlarm().getId(),
                explanation.getExplanationText(),
                explanation.getLlmModel(),
                explanation.getLlmPromptVersion(),
                explanation.getGeneratedAt()
        );
    }
}
