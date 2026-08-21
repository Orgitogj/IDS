package com.diploma.idsml.repository;

import com.diploma.idsml.entity.MLModel;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface MLModelRepository extends JpaRepository<MLModel, UUID> {

    Optional<MLModel> findByName(String name);

    Optional<MLModel> findByActiveTrue();
}
