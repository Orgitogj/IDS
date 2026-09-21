package com.diploma.idsml.service;

import com.diploma.idsml.dto.MLModelCreateRequest;
import com.diploma.idsml.dto.MLModelResponse;
import com.diploma.idsml.entity.MLModel;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.MLModelRepository;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class MLModelService {

    public static final String ACTIVE_MODEL_TOPIC = "/topic/models/active";

    private final MLModelRepository mlModelRepository;
    private final SimpMessagingTemplate messagingTemplate;
    private final MlServiceClient mlServiceClient;

    public MLModelService(MLModelRepository mlModelRepository,
                          SimpMessagingTemplate messagingTemplate,
                          MlServiceClient mlServiceClient) {
        this.mlModelRepository = mlModelRepository;
        this.messagingTemplate = messagingTemplate;
        this.mlServiceClient = mlServiceClient;
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
        MLModel model = findEntity(id);
        mlServiceClient.activate(model.getId());

        mlModelRepository.findByActiveTrue().ifPresent(current -> {
            current.setActive(false);
            mlModelRepository.save(current);
        });

        model.setActive(true);
        MLModelResponse response = toResponse(mlModelRepository.save(model));
        messagingTemplate.convertAndSend(ACTIVE_MODEL_TOPIC, response);
        return response;
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
                .orElseThrow(() -> new ResourceNotFoundException("Modeli nuk u gjet: " + id));
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