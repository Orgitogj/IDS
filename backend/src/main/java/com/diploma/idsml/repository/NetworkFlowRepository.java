package com.diploma.idsml.repository;

import com.diploma.idsml.entity.DatasetSource;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.entity.NetworkFlow;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface NetworkFlowRepository extends JpaRepository<NetworkFlow, UUID> {

    List<NetworkFlow> findByDatasetSource(DatasetSource datasetSource);

    List<NetworkFlow> findByLabel(FlowLabel label);

    List<NetworkFlow> findBySourceIp(String sourceIp);

    List<NetworkFlow> findByDestinationIp(String destinationIp);
}
