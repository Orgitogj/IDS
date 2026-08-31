package com.diploma.idsml.repository;

import com.diploma.idsml.entity.AlarmStatus;
import com.diploma.idsml.entity.AnalystFeedback;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.UUID;

public interface AnalystFeedbackRepository extends JpaRepository<AnalystFeedback, UUID> {

    Page<AnalystFeedback> findAllByOrderByCreatedAtDesc(Pageable pageable);

    List<AnalystFeedback> findByAnalystVerdict(AlarmStatus analystVerdict);

    boolean existsByAlarmIdAndAnalystVerdict(UUID alarmId, AlarmStatus analystVerdict);

    @Query("SELECT f.analystVerdict, COUNT(f) FROM AnalystFeedback f GROUP BY f.analystVerdict")
    List<Object[]> countGroupedByVerdict();

    @Query("SELECT f.modelName, f.analystVerdict, COUNT(f) FROM AnalystFeedback f "
            + "GROUP BY f.modelName, f.analystVerdict")
    List<Object[]> countGroupedByModelAndVerdict();
}
