package com.diploma.idsml.repository;

import com.diploma.idsml.entity.ExperimentResult;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface ExperimentResultRepository extends JpaRepository<ExperimentResult, UUID> {

    List<ExperimentResult> findByMlModelId(UUID mlModelId);

    List<ExperimentResult> findByTestedOnDataset(String testedOnDataset);
}
