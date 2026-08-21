package com.diploma.idsml.repository;

import com.diploma.idsml.entity.Alarm;
import com.diploma.idsml.entity.AlarmStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface AlarmRepository extends JpaRepository<Alarm, UUID> {

    List<Alarm> findByStatus(AlarmStatus status);

    Optional<Alarm> findByNetworkFlowId(UUID networkFlowId);
}
