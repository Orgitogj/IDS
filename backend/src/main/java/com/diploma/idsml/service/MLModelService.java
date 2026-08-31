package com.diploma.idsml.service;

import com.diploma.idsml.dto.MLModelCreateRequest;
import com.diploma.idsml.dto.MLModelResponse;
import com.diploma.idsml.entity.MLModel;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.MLModelRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class MLModelService {

    private final MLModelRepository mlModelRepository;

    public MLModelService(MLModelRepository mlModelRepository) {
        this.mlModelRepository = mlModelRepository;
    }

    public List<MLModelResponse> getAll() {
        return mlModelRepository.findAll().stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    public MLModelResponse getById(UUID id) {
        return toResponse(findEntity(id));
    }

    public MLModelResponse getActive() {
        return mlModelRepository.findByActiveTrue()
                .map(this::toResponse)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Asnje model aktiv - aktivizo nje model me PATCH /api/models/{id}/activate."));
    }

    @Transactional
    public MLModelResponse setActive(UUID id) {
        mlModelRepository.findByActiveTrue().ifPresent(current -> {
            current.setActive(false);
            mlModelRepository.save(current);
        });

        MLModel model = findEntity(id);
        model.setActive(true);
        return toResponse(mlModelRepository.save(model));
    }

    @Transactional
    public MLModelResponse create(MLModelCreateRequest request) {
        MLModel model = MLModel.builder()
                .algorithm(request.algorithm())
                .name(request.name())
                .version(request.version() != null && !request.version().isBlank()
                        ? request.version()
                        : "1.0")
                .featureVersion(request.featureVersion())
                .trainedOnDataset(request.trainedOnDataset())
                .artifactPath(request.artifactPath())
                .hyperparameters(request.hyperparameters())
                .featureSet(request.featureSet())
                .active(false)
                .trainedAt(request.trainedAt())
                .build();

        return toResponse(mlModelRepository.save(model));
    }

    private MLModel findEntity(UUID id) {
        return mlModelRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("MLModel s'u gjet: " + id));
    }

    private MLModelResponse toResponse(MLModel model) {
        return new MLModelResponse(
                model.getId(),
                model.getAlgorithm(),
                model.getName(),
                model.getVersion(),
                model.getFeatureVersion(),
                model.getTrainedOnDataset(),
                model.getArtifactPath(),
                model.getHyperparameters(),
                model.getFeatureSet(),
                model.isActive(),
                model.getTrainedAt(),
                model.getCreatedAt()
        );
    }
}