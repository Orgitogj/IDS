package com.diploma.idsml.repository;

import com.diploma.idsml.entity.SeverityThresholds;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface SeverityThresholdsRepository extends JpaRepository<SeverityThresholds, UUID> {
}
