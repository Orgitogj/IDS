package com.diploma.idsml.repository;

import com.diploma.idsml.entity.Explanation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface ExplanationRepository extends JpaRepository<Explanation, UUID> {

    Optional<Explanation> findByAlarmId(UUID alarmId);
}
