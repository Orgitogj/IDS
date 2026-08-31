package com.diploma.idsml.repository;

import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.Incident;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface IncidentRepository extends JpaRepository<Incident, UUID>,
        JpaSpecificationExecutor<Incident> {

    @Query(value = "SELECT pg_advisory_xact_lock(hashtext(:key))", nativeQuery = true)
    void lockCorrelationKey(@Param("key") String key);

    @Query("""
            SELECT i FROM Incident i
            WHERE i.correlationKey = :key
              AND i.status NOT IN (com.diploma.idsml.entity.AlarmStatus.RESOLVED,
                                   com.diploma.idsml.entity.AlarmStatus.FALSE_POSITIVE)
              AND i.lastSeen >= :notBefore
            ORDER BY i.lastSeen DESC
            """)
    List<Incident> findOpenByCorrelationKey(@Param("key") String key,
                                            @Param("notBefore") Instant notBefore);

    List<Incident> findByStatus(AlarmStatus status);

    @Query("SELECT i.status, COUNT(i) FROM Incident i GROUP BY i.status")
    List<Object[]> countGroupedByStatus();

    @Query("SELECT i.severity, COUNT(i) FROM Incident i GROUP BY i.severity")
    List<Object[]> countGroupedBySeverity();

    @Query("""
            SELECT COUNT(DISTINCT f.destinationIp)
            FROM Alarm a JOIN a.networkFlow f
            WHERE a.incident.id = :incidentId
            """)
    long countDistinctDestinations(@Param("incidentId") UUID incidentId);
}
