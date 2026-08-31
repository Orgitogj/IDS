package com.diploma.idsml.repository;

import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AlarmRepository extends JpaRepository<Alarm, UUID>,
        JpaSpecificationExecutor<Alarm> {

    List<Alarm> findByStatus(AlarmStatus status);

    List<Alarm> findByIncidentIdOrderByCreatedAtDesc(UUID incidentId);

    Optional<Alarm> findByNetworkFlowId(UUID networkFlowId);

    @Query("SELECT a.severity, COUNT(a) FROM Alarm a GROUP BY a.severity")
    List<Object[]> countGroupedBySeverity();

    @Query("SELECT a.status, COUNT(a) FROM Alarm a GROUP BY a.status")
    List<Object[]> countGroupedByStatus();

    @Query(value = """
            SELECT to_char(date_trunc('hour', created_at AT TIME ZONE 'UTC'),
                           'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS bucket,
                   COUNT(*)
            FROM alarms
            WHERE created_at >= now() - INTERVAL '24 hours'
            GROUP BY bucket
            ORDER BY bucket
            """, nativeQuery = true)
    List<Object[]> countGroupedByHour();

    @Query(value = """
            SELECT f.source_ip,
                   f.attack_type,
                   COUNT(*) AS alarm_count,
                   MIN(CASE a.severity
                           WHEN 'CRITICAL' THEN 1
                           WHEN 'HIGH' THEN 2
                           WHEN 'MEDIUM' THEN 3
                           ELSE 4
                       END) AS severity_rank,
                   to_char(MIN(a.created_at) AT TIME ZONE 'UTC',
                           'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS first_seen,
                   to_char(MAX(a.created_at) AT TIME ZONE 'UTC',
                           'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_seen
            FROM alarms a
            JOIN network_flows f ON a.network_flow_id = f.id
            WHERE f.source_ip IS NOT NULL
            GROUP BY f.source_ip, f.attack_type
            ORDER BY alarm_count DESC
            LIMIT :limit
            """, nativeQuery = true)
    List<Object[]> findIncidents(@Param("limit") int limit);
}
