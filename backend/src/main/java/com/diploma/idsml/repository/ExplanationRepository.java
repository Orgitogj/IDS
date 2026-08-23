package com.diploma.idsml.repository;

import com.diploma.idsml.entity.Explanation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface ExplanationRepository extends JpaRepository<Explanation, UUID> {

    List<Explanation> findByAlarmIdOrderByGeneratedAtAsc(UUID alarmId);
}
