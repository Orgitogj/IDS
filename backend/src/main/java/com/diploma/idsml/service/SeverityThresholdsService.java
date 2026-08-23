package com.diploma.idsml.service;

import com.diploma.idsml.dto.SeverityThresholdsResponse;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.SeverityThresholds;
import com.diploma.idsml.exception.InvalidRequestException;
import com.diploma.idsml.repository.SeverityThresholdsRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

@Service
public class SeverityThresholdsService {

    private final SeverityThresholdsRepository repository;

    private volatile SeverityThresholds cached;

    public SeverityThresholdsService(SeverityThresholdsRepository repository) {
        this.repository = repository;
    }

    public SeverityThresholdsResponse get() {
        return toResponse(current());
    }

    @Transactional
    public SeverityThresholdsResponse update(Double criticalMin, Double highMin, Double mediumMin) {
        if (!(criticalMin > highMin && highMin > mediumMin)) {
            throw new InvalidRequestException(
                    "Pragjet duhet te jene ne rend zbrites: critical > high > medium.");
        }

        SeverityThresholds thresholds = current();
        thresholds.setCriticalMin(criticalMin);
        thresholds.setHighMin(highMin);
        thresholds.setMediumMin(mediumMin);
        thresholds.setUpdatedAt(Instant.now());

        SeverityThresholds saved = repository.save(thresholds);
        cached = saved;

        return toResponse(saved);
    }

    public AlarmSeverity resolveSeverity(Double confidence) {
        if (confidence == null) {
            return AlarmSeverity.MEDIUM;
        }

        SeverityThresholds thresholds = current();
        if (confidence >= thresholds.getCriticalMin()) return AlarmSeverity.CRITICAL;
        if (confidence >= thresholds.getHighMin()) return AlarmSeverity.HIGH;
        if (confidence >= thresholds.getMediumMin()) return AlarmSeverity.MEDIUM;
        return AlarmSeverity.LOW;
    }

    private SeverityThresholds current() {
        SeverityThresholds local = cached;
        if (local == null) {
            local = repository.findById(SeverityThresholds.SINGLETON_ID)
                    .orElseGet(() -> repository.save(SeverityThresholds.builder()
                            .criticalMin(0.95)
                            .highMin(0.85)
                            .mediumMin(0.70)
                            .build()));
            cached = local;
        }
        return local;
    }

    private SeverityThresholdsResponse toResponse(SeverityThresholds thresholds) {
        return new SeverityThresholdsResponse(
                thresholds.getCriticalMin(),
                thresholds.getHighMin(),
                thresholds.getMediumMin(),
                thresholds.getUpdatedAt()
        );
    }
}
