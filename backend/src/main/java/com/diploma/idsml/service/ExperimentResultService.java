package com.diploma.idsml.service;

import com.diploma.idsml.dto.ExperimentResultResponse;
import com.diploma.idsml.entity.ExperimentResult;
import com.diploma.idsml.entity.MLModel;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.ExperimentResultRepository;
import com.diploma.idsml.repository.MLModelRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class ExperimentResultService {

    private final ExperimentResultRepository experimentResultRepository;
    private final MLModelRepository mlModelRepository;

    public ExperimentResultService(ExperimentResultRepository experimentResultRepository,
                                    MLModelRepository mlModelRepository) {
        this.experimentResultRepository = experimentResultRepository;
        this.mlModelRepository = mlModelRepository;
    }

    public List<ExperimentResultResponse> getAll() {
        return experimentResultRepository.findAll().stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    public List<ExperimentResultResponse> getByModelId(UUID modelId) {
        return experimentResultRepository.findByMlModelId(modelId).stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    public ExperimentResultResponse getById(UUID id) {
        return experimentResultRepository.findById(id)
                .map(this::toResponse)
                .orElseThrow(() -> new ResourceNotFoundException("ExperimentResult s'u gjet: " + id));
    }

    @Transactional
    public ExperimentResultResponse recordResult(UUID modelId, String testedOnDataset,
                                                   String featureSetUsed, Double accuracy,
                                                   Double precisionScore, Double recall,
                                                   Double f1Score, Double avgLatencyMs,
                                                   Long sampleSize, String notes) {
        MLModel model = mlModelRepository.findById(modelId)
                .orElseThrow(() -> new ResourceNotFoundException("MLModel s'u gjet: " + modelId));

        ExperimentResult result = ExperimentResult.builder()
                .mlModel(model)
                .testedOnDataset(testedOnDataset)
                .featureSetUsed(featureSetUsed)
                .accuracy(accuracy)
                .precisionScore(precisionScore)
                .recall(recall)
                .f1Score(f1Score)
                .avgLatencyMs(avgLatencyMs)
                .sampleSize(sampleSize)
                .notes(notes)
                .build();

        return toResponse(experimentResultRepository.save(result));
    }

    private ExperimentResultResponse toResponse(ExperimentResult result) {
        return new ExperimentResultResponse(
                result.getId(),
                result.getMlModel().getId(),
                result.getMlModel().getName(),
                result.getTestedOnDataset(),
                result.getFeatureSetUsed(),
                result.getAccuracy(),
                result.getPrecisionScore(),
                result.getRecall(),
                result.getF1Score(),
                result.getAvgLatencyMs(),
                result.getSampleSize(),
                result.getNotes(),
                result.getRanAt()
        );
    }
}
