package com.diploma.idsml.service;

import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmSeverity;
import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.DetectionMethod;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.entity.Incident;
import com.diploma.idsml.entity.NetworkFlow;
import com.diploma.idsml.repository.IncidentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class IncidentServiceTest {

    private static final Instant T0 = Instant.parse("2026-08-31T10:00:00Z");
    private static final long WINDOW_SECONDS = 120;

    @Mock
    private IncidentRepository incidentRepository;

    private IncidentService service;

    @BeforeEach
    void setUp() {
        service = new IncidentService(incidentRepository, WINDOW_SECONDS);
        lenient().when(incidentRepository.save(any(Incident.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
    }

    private NetworkFlow flow(String sourceIp, String destinationIp, String attackType,
                             Instant at) {
        return NetworkFlow.builder()
                .sourceIp(sourceIp)
                .destinationIp(destinationIp)
                .attackType(attackType)
                .detectionMethod(DetectionMethod.SUPERVISED_ML)
                .predictedLabel(FlowLabel.ATTACK)
                .flowTimestamp(at)
                .build();
    }

    private Alarm alarm(AlarmSeverity severity) {
        return Alarm.builder().severity(severity).status(AlarmStatus.NEW).build();
    }

    @Test
    void theCorrelationKeyPairsSourceWithAttackType() {
        assertThat(IncidentService.correlationKey(flow("10.0.0.5", "10.0.0.9", "PortScan", T0)))
                .isEqualTo("10.0.0.5|PortScan");
    }

    @Test
    void anAnomalyWithoutAnAttackTypeGetsItsOwnKey() {
        assertThat(IncidentService.correlationKey(flow("10.0.0.5", "10.0.0.9", null, T0)))
                .isEqualTo("10.0.0.5|UNKNOWN");
    }

    @Test
    void theConfiguredWindowIsUsed() {
        assertThat(service.getCorrelationWindow()).isEqualTo(Duration.ofSeconds(WINDOW_SECONDS));
    }

    @Test
    void theFirstAlarmOpensAnIncident() {
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of());

        Incident incident = service.correlate(alarm(AlarmSeverity.HIGH),
                flow("10.0.0.5", "10.0.0.9", "PortScan", T0));

        assertThat(incident.getCorrelationKey()).isEqualTo("10.0.0.5|PortScan");
        assertThat(incident.getSourceIp()).isEqualTo("10.0.0.5");
        assertThat(incident.getAttackType()).isEqualTo("PortScan");
        assertThat(incident.getAlarmCount()).isEqualTo(1);
        assertThat(incident.getFlowCount()).isEqualTo(1);
        assertThat(incident.getSeverity()).isEqualTo(AlarmSeverity.HIGH);
        assertThat(incident.getStatus()).isEqualTo(AlarmStatus.NEW);
        assertThat(incident.getFirstSeen()).isEqualTo(T0);
        assertThat(incident.getLastSeen()).isEqualTo(T0);
        assertThat(incident.getDestinationIps()).containsExactly("10.0.0.9");
    }

    @Test
    void theCorrelationKeyIsLockedBeforeLookup() {
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of());

        service.correlate(alarm(AlarmSeverity.LOW), flow("10.0.0.5", "10.0.0.9", "Bot", T0));

        verify(incidentRepository).lockCorrelationKey("10.0.0.5|Bot");
    }

    @Test
    void aLaterAlarmInsideTheWindowJoinsTheSameIncident() {
        Incident existing = openIncident("10.0.0.5|PortScan", T0, AlarmSeverity.MEDIUM);
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of(existing));

        Incident incident = service.correlate(alarm(AlarmSeverity.MEDIUM),
                flow("10.0.0.5", "10.0.0.11", "PortScan", T0.plusSeconds(60)));

        assertThat(incident).isSameAs(existing);
        assertThat(incident.getAlarmCount()).isEqualTo(2);
        assertThat(incident.getLastSeen()).isEqualTo(T0.plusSeconds(60));
        assertThat(incident.getFirstSeen()).isEqualTo(T0);
        assertThat(incident.getDestinationIps()).containsExactly("10.0.0.9", "10.0.0.11");
    }

    @Test
    void theLookupOnlyConsidersIncidentsInsideTheWindow() {
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of());

        Instant observedAt = T0.plusSeconds(500);
        service.correlate(alarm(AlarmSeverity.LOW),
                flow("10.0.0.5", "10.0.0.9", "PortScan", observedAt));

        ArgumentCaptor<Instant> notBefore = ArgumentCaptor.forClass(Instant.class);
        verify(incidentRepository).findOpenByCorrelationKey(anyString(), notBefore.capture());
        assertThat(notBefore.getValue()).isEqualTo(observedAt.minusSeconds(WINDOW_SECONDS));
    }

    @Test
    void severityEscalatesButNeverDowngrades() {
        Incident existing = openIncident("10.0.0.5|DDoS", T0, AlarmSeverity.MEDIUM);
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of(existing));

        service.correlate(alarm(AlarmSeverity.CRITICAL),
                flow("10.0.0.5", "10.0.0.9", "DDoS", T0.plusSeconds(10)));
        assertThat(existing.getSeverity()).isEqualTo(AlarmSeverity.CRITICAL);

        service.correlate(alarm(AlarmSeverity.LOW),
                flow("10.0.0.5", "10.0.0.9", "DDoS", T0.plusSeconds(20)));
        assertThat(existing.getSeverity()).isEqualTo(AlarmSeverity.CRITICAL);
    }

    @Test
    void anEarlierTimestampMovesFirstSeenBackwards() {
        Incident existing = openIncident("10.0.0.5|DDoS", T0, AlarmSeverity.LOW);
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of(existing));

        service.correlate(alarm(AlarmSeverity.LOW),
                flow("10.0.0.5", "10.0.0.9", "DDoS", T0.minusSeconds(30)));

        assertThat(existing.getFirstSeen()).isEqualTo(T0.minusSeconds(30));
        assertThat(existing.getLastSeen()).isEqualTo(T0);
    }

    @Test
    void theAlarmIsLinkedToTheIncident() {
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of());

        Alarm alarm = alarm(AlarmSeverity.HIGH);
        Incident incident = service.correlate(alarm,
                flow("10.0.0.5", "10.0.0.9", "PortScan", T0));

        assertThat(alarm.getIncident()).isSameAs(incident);
    }

    @Test
    void duplicateDestinationsAreNotTrackedTwice() {
        Incident existing = openIncident("10.0.0.5|PortScan", T0, AlarmSeverity.LOW);
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of(existing));

        service.correlate(alarm(AlarmSeverity.LOW),
                flow("10.0.0.5", "10.0.0.9", "PortScan", T0.plusSeconds(5)));

        assertThat(existing.getDestinationIps()).containsExactly("10.0.0.9");
    }

    @Test
    void destinationTrackingIsCappedAndFlagged() {
        Incident incident = openIncident("10.0.0.5|PortScan", T0, AlarmSeverity.LOW);
        incident.getDestinationIps().clear();

        for (int i = 0; i < Incident.MAX_TRACKED_DESTINATIONS + 25; i++) {
            incident.trackDestination("10.1." + (i / 256) + "." + (i % 256));
        }

        assertThat(incident.getDestinationIps()).hasSize(Incident.MAX_TRACKED_DESTINATIONS);
        assertThat(incident.isDestinationsTruncated()).isTrue();
    }

    @Test
    void aResolvedIncidentIsNotOpen() {
        Incident incident = openIncident("10.0.0.5|PortScan", T0, AlarmSeverity.LOW);
        assertThat(incident.isOpen()).isTrue();

        incident.setStatus(AlarmStatus.RESOLVED);
        assertThat(incident.isOpen()).isFalse();

        incident.setStatus(AlarmStatus.FALSE_POSITIVE);
        assertThat(incident.isOpen()).isFalse();

        incident.setStatus(AlarmStatus.ACKNOWLEDGED);
        assertThat(incident.isOpen()).isTrue();
    }

    @Test
    void updatingStatusPersistsTheNewStatus() {
        Incident incident = openIncident("10.0.0.5|PortScan", T0, AlarmSeverity.LOW);
        given(incidentRepository.findById(incident.getId())).willReturn(Optional.of(incident));

        service.updateStatus(incident.getId(), AlarmStatus.CONFIRMED);

        assertThat(incident.getStatus()).isEqualTo(AlarmStatus.CONFIRMED);
    }

    @Test
    void aFlowWithoutATimestampFallsBackToTheAlarmTime() {
        lenient().when(incidentRepository.findOpenByCorrelationKey(anyString(), any()))
                .thenReturn(List.of());

        Alarm alarm = alarm(AlarmSeverity.LOW);
        NetworkFlow withoutTimestamp = flow("10.0.0.5", "10.0.0.9", "Bot", null);

        Incident incident = service.correlate(alarm, withoutTimestamp);

        assertThat(incident.getFirstSeen()).isEqualTo(alarm.getCreatedAt());
    }

    private Incident openIncident(String key, Instant at, AlarmSeverity severity) {
        return Incident.builder()
                .correlationKey(key)
                .sourceIp(key.split("\\|")[0])
                .attackType(key.split("\\|")[1])
                .firstSeen(at)
                .lastSeen(at)
                .severity(severity)
                .status(AlarmStatus.NEW)
                .alarmCount(1)
                .flowCount(1)
                .destinationIps(new java.util.ArrayList<>(List.of("10.0.0.9")))
                .build();
    }
}
