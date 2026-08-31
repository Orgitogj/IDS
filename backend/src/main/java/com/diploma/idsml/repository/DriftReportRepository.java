package com.diploma.idsml.repository;

import com.diploma.idsml.entity.DriftReport;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface DriftReportRepository extends JpaRepository<DriftReport, UUID> {

    Optional<DriftReport> findFirstByOrderByGeneratedAtDesc();

    Page<DriftReport> findAllByOrderByGeneratedAtDesc(Pageable pageable);
}
