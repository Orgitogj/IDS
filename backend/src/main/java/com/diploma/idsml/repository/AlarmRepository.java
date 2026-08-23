package com.diploma.idsml.repository;

import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AlarmRepository extends JpaRepository<Alarm, UUID>,
        JpaSpecificationExecutor<Alarm> {

    List<Alarm> findByStatus(AlarmStatus status);

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
}
