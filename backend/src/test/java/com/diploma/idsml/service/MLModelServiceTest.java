package com.diploma.idsml.service;

import com.diploma.idsml.dto.MLModelResponse;
import com.diploma.idsml.entity.MLModel;
import com.diploma.idsml.exception.ModelActivationException;
import com.diploma.idsml.exception.ResourceNotFoundException;
import com.diploma.idsml.repository.MLModelRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.messaging.simp.SimpMessagingTemplate;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MLModelServiceTest {

    @Mock
    private MLModelRepository mlModelRepository;

    @Mock
    private SimpMessagingTemplate messagingTemplate;

    @Mock
    private MlServiceClient mlServiceClient;

    @InjectMocks
    private MLModelService mlModelService;

    private MLModel model(String name, boolean active) {
        return MLModel.builder()
                .algorithm("XGBoost")
                .name(name)
                .trainedOnDataset("CICIDS2017")
                .artifactPath("models/" + name + ".joblib")
                .active(active)
                .build();
    }

    @Test
    void activatingAModelLoadsItInTheMlServiceBeforeTheRegistryChanges() {
        MLModel previous = model("previous", true);
        MLModel next = model("next", false);
        when(mlModelRepository.findById(next.getId())).thenReturn(Optional.of(next));
        when(mlModelRepository.findByActiveTrue()).thenReturn(Optional.of(previous));
        when(mlModelRepository.save(any(MLModel.class))).thenAnswer(call -> call.getArgument(0));

        mlModelService.setActive(next.getId());

        InOrder order = inOrder(mlServiceClient, mlModelRepository);
        order.verify(mlServiceClient).activate(next.getId());
        order.verify(mlModelRepository).save(previous);
        assertThat(previous.isActive()).isFalse();
        assertThat(next.isActive()).isTrue();
    }

    @Test
    void activatingAModelBroadcastsItAsTheNewActiveModel() {
        MLModel next = model("next", false);
        when(mlModelRepository.findById(next.getId())).thenReturn(Optional.of(next));
        when(mlModelRepository.findByActiveTrue()).thenReturn(Optional.empty());
        when(mlModelRepository.save(any(MLModel.class))).thenAnswer(call -> call.getArgument(0));

        MLModelResponse response = mlModelService.setActive(next.getId());

        ArgumentCaptor<MLModelResponse> sent = ArgumentCaptor.forClass(MLModelResponse.class);
        verify(messagingTemplate).convertAndSend(eq(MLModelService.ACTIVE_MODEL_TOPIC), sent.capture());
        assertThat(sent.getValue()).isEqualTo(response);
        assertThat(sent.getValue().id()).isEqualTo(next.getId());
        assertThat(sent.getValue().active()).isTrue();
    }

    @Test
    void aModelTheMlServiceRefusesLeavesTheRegistryUnchanged() {
        MLModel mlp = model("mlp", false);
        when(mlModelRepository.findById(mlp.getId())).thenReturn(Optional.of(mlp));
        doThrow(new ModelActivationException("lejohen vetem modele XGBoost."))
                .when(mlServiceClient).activate(mlp.getId());

        assertThatThrownBy(() -> mlModelService.setActive(mlp.getId()))
                .isInstanceOf(ModelActivationException.class);

        assertThat(mlp.isActive()).isFalse();
        verify(mlModelRepository, never()).save(any(MLModel.class));
        verify(messagingTemplate, never()).convertAndSend(anyString(), any(Object.class));
    }

    @Test
    void activatingAnUnknownModelNeverReachesTheMlService() {
        MLModel unknown = model("unknown", false);
        when(mlModelRepository.findById(unknown.getId())).thenReturn(Optional.empty());

        assertThatThrownBy(() -> mlModelService.setActive(unknown.getId()))
                .isInstanceOf(ResourceNotFoundException.class);

        verifyNoInteractions(mlServiceClient, messagingTemplate);
    }
}
