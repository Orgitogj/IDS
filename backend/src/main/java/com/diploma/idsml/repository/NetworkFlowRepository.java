package com.diploma.idsml.repository;

import com.diploma.idsml.entity.NetworkFlow;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.UUID;

public interface NetworkFlowRepository extends JpaRepository<NetworkFlow, UUID>,
        JpaSpecificationExecutor<NetworkFlow> {

    @Query("""
            SELECT f.attackType, COUNT(f)
            FROM NetworkFlow f
            WHERE f.attackType IS NOT NULL
            GROUP BY f.attackType
            ORDER BY COUNT(f) DESC
            """)
    List<Object[]> countGroupedByAttackType();
}
