package com.diploma.idsml.service;

import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.AnalystFeedback;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.entity.Incident;
import com.diploma.idsml.entity.NetworkFlow;
import com.diploma.idsml.repository.AnalystFeedbackRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class AnalystFeedbackServiceTest {

    private static final UUID MODEL_ID = UUID.randomUUID();

    @Mock
    private AnalystFeedbackRepository feedbackRepository;

    private AnalystFeedbackService service;

    @BeforeEach
    void setUp() {
        service = new AnalystFeedbackService(feedbackRepository, new ObjectMapper());
        lenient().when(feedbackRepository.save(any(AnalystFeedback.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
    }

    private NetworkFlow flow() {
        return NetworkFlow.builder()
                .predictedLabel(FlowLabel.ATTACK)
                .attackType("PortScan")
                .groundTruthAttackType("PortScan")
                .predictionConfidence(0.96)
                .anomalyScore(0.42)
                .detectionMethod(DetectionMethod.SUPERVISED_ML)
                .modelId(MODEL_ID)
                .modelName("xgb-smote-top50features-v1")
                .modelVersion("1.0")
                .featureVersion("cicids2017-top50-v1")
                .featureVector(Map.of("Flow Duration", 1234.0))
                .build();
    }

    private Alarm alarm(NetworkFlow flow) {
        return Alarm.builder()
                .networkFlow(flow)
                .severity(AlarmSeverity.CRITICAL)
                .status(AlarmStatus.NEW)
                .build();
    }

    @Test
    void falsePositiveAndConfirmedAreTheRecordableVerdicts() {
        assertThat(AnalystFeedbackService.isRecordable(AlarmStatus.FALSE_POSITIVE)).isTrue();
        assertThat(AnalystFeedbackService.isRecordable(AlarmStatus.CONFIRMED)).isTrue();
    }

    @ParameterizedTest
    @EnumSource(value = AlarmStatus.class,
            names = {"NEW", "ACKNOWLEDGED", "RESOLVED"})
    void otherStatusesAreNotRecorded(AlarmStatus status) {
        assertThat(AnalystFeedbackService.isRecordable(status)).isFalse();

        service.record(alarm(flow()), status, "analyst-1");

        verify(feedbackRepository, never()).save(any());
    }

    @Test
    void aFalsePositiveVerdictSnapshotsTheDetection() {
        NetworkFlow flow = flow();
        Alarm alarm = alarm(flow);

        service.record(alarm, AlarmStatus.FALSE_POSITIVE, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());
        AnalystFeedback saved = captor.getValue();

        assertThat(saved.getAlarmId()).isEqualTo(alarm.getId());
        assertThat(saved.getNetworkFlowId()).isEqualTo(flow.getId());
        assertThat(saved.getAnalystVerdict()).isEqualTo(AlarmStatus.FALSE_POSITIVE);
        assertThat(saved.getAnalystUsername()).isEqualTo("analyst-1");
        assertThat(saved.getOriginalPrediction()).isEqualTo(FlowLabel.ATTACK);
        assertThat(saved.getOriginalAttackType()).isEqualTo("PortScan");
        assertThat(saved.getOriginalConfidence()).isEqualTo(0.96);
        assertThat(saved.getOriginalAnomalyScore()).isEqualTo(0.42);
        assertThat(saved.getDetectionMethod()).isEqualTo(DetectionMethod.SUPERVISED_ML);
    }

    @Test
    void theModelThatProducedTheDetectionIsRecorded() {
        service.record(alarm(flow()), AlarmStatus.FALSE_POSITIVE, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());

        assertThat(captor.getValue().getModelId()).isEqualTo(MODEL_ID);
        assertThat(captor.getValue().getModelName()).isEqualTo("xgb-smote-top50features-v1");
        assertThat(captor.getValue().getModelVersion()).isEqualTo("1.0");
        assertThat(captor.getValue().getFeatureVersion()).isEqualTo("cicids2017-top50-v1");
    }

    @Test
    void theFeatureVectorIsSnapshottedSoItSurvivesModelChanges() {
        service.record(alarm(flow()), AlarmStatus.FALSE_POSITIVE, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());

        assertThat(captor.getValue().getFeatureVector()).containsEntry("Flow Duration", 1234.0);
    }

    @Test
    void groundTruthIsCarriedThroughWhenKnown() {
        service.record(alarm(flow()), AlarmStatus.CONFIRMED, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());

        assertThat(captor.getValue().getGroundTruthLabel()).isEqualTo("PortScan");
    }

    @Test
    void aConfirmedVerdictKeepsTheAttackTypeAsTheAnalystClassification() {
        service.record(alarm(flow()), AlarmStatus.CONFIRMED, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());

        assertThat(captor.getValue().getAnalystAttackType()).isEqualTo("PortScan");
    }

    @Test
    void aFalsePositiveVerdictClaimsNoAttackType() {
        service.record(alarm(flow()), AlarmStatus.FALSE_POSITIVE, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());

        assertThat(captor.getValue().getAnalystAttackType()).isNull();
    }

    @Test
    void theIncidentIsLinkedWhenTheAlarmBelongsToOne() {
        Alarm alarm = alarm(flow());
        Incident incident = Incident.builder().correlationKey("10.0.0.1|PortScan").build();
        alarm.setIncident(incident);

        service.record(alarm, AlarmStatus.CONFIRMED, "analyst-1");

        ArgumentCaptor<AnalystFeedback> captor = ArgumentCaptor.forClass(AnalystFeedback.class);
        verify(feedbackRepository).save(captor.capture());

        assertThat(captor.getValue().getIncidentId()).isEqualTo(incident.getId());
    }

    @Test
    void theSameVerdictIsNotRecordedTwiceForTheSameAlarm() {
        Alarm alarm = alarm(flow());
        given(feedbackRepository.existsByAlarmIdAndAnalystVerdict(alarm.getId(),
                AlarmStatus.FALSE_POSITIVE)).willReturn(true);

        service.record(alarm, AlarmStatus.FALSE_POSITIVE, "analyst-1");

        verify(feedbackRepository, never()).save(any());
    }

    @Test
    void statsReportTheFalsePositiveRate() {
        given(feedbackRepository.countGroupedByVerdict()).willReturn(List.of(
                new Object[]{AlarmStatus.FALSE_POSITIVE, 3L},
                new Object[]{AlarmStatus.CONFIRMED, 7L}
        ));
        given(feedbackRepository.countGroupedByModelAndVerdict()).willReturn(List.of(
                new Object[]{"xgb-smote-top50features-v1", AlarmStatus.FALSE_POSITIVE, 3L},
                new Object[]{"xgb-smote-top50features-v1", AlarmStatus.CONFIRMED, 7L}
        ));

        var stats = service.getStats();

        assertThat(stats.totalFeedback()).isEqualTo(10);
        assertThat(stats.falsePositiveRate()).isEqualTo(0.3);
        assertThat(stats.verdictCounts()).containsEntry("FALSE_POSITIVE", 3L);
        assertThat(stats.byModel().get("xgb-smote-top50features-v1"))
                .containsEntry("CONFIRMED", 7L);
    }

    @Test
    void statsAreSafeWhenThereIsNoFeedbackYet() {
        given(feedbackRepository.countGroupedByVerdict()).willReturn(List.of());
        given(feedbackRepository.countGroupedByModelAndVerdict()).willReturn(List.of());

        var stats = service.getStats();

        assertThat(stats.totalFeedback()).isZero();
        assertThat(stats.falsePositiveRate()).isZero();
    }

    @Test
    void exportProducesOneJsonObjectPerLine() throws Exception {
        NetworkFlow flow = flow();
        Alarm alarm = alarm(flow);
        AnalystFeedback one = buildFeedback(alarm, flow, AlarmStatus.FALSE_POSITIVE);
        AnalystFeedback two = buildFeedback(alarm, flow, AlarmStatus.CONFIRMED);
        given(feedbackRepository.findAll()).willReturn(List.of(one, two));

        String jsonl = service.exportAsJsonl();
        String[] lines = jsonl.strip().split("\n");

        assertThat(lines).hasSize(2);

        ObjectMapper mapper = new ObjectMapper();
        Map<String, Object> first = mapper.readValue(lines[0],
                new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {});
        assertThat(first).containsKeys("feedback_id", "alarm_id", "analyst_verdict",
                "model_name", "feature_version", "features", "ground_truth_label");
        assertThat(first.get("analyst_verdict")).isEqualTo("FALSE_POSITIVE");
    }

    @Test
    void exportIsEmptyWhenNoFeedbackExists() {
        given(feedbackRepository.findAll()).willReturn(List.of());
        assertThat(service.exportAsJsonl()).isEmpty();
    }

    private AnalystFeedback buildFeedback(Alarm alarm, NetworkFlow flow, AlarmStatus verdict) {
        return AnalystFeedback.builder()
                .alarmId(alarm.getId())
                .networkFlowId(flow.getId())
                .originalPrediction(FlowLabel.ATTACK)
                .originalAttackType("PortScan")
                .originalConfidence(0.96)
                .detectionMethod(DetectionMethod.SUPERVISED_ML)
                .analystVerdict(verdict)
                .analystUsername("analyst-1")
                .modelId(MODEL_ID)
                .modelName("xgb-smote-top50features-v1")
                .modelVersion("1.0")
                .featureVersion("cicids2017-top50-v1")
                .featureVector(Map.of("Flow Duration", 1234.0))
                .groundTruthLabel("PortScan")
                .build();
    }
}
