package com.diploma.idsml.repository;

import com.diploma.idsml.entity.AppUser;
import com.diploma.idsml.entity.RefreshToken;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, UUID> {

    Optional<RefreshToken> findByTokenHash(String tokenHash);

    @Modifying
    @Query("update RefreshToken t set t.revokedAt = :moment "
            + "where t.user = :user and t.revokedAt is null")
    int revokeAllForUser(@Param("user") AppUser user, @Param("moment") Instant moment);

    @Modifying
    @Query("delete from RefreshToken t where t.expiresAt < :moment")
    int deleteExpiredBefore(@Param("moment") Instant moment);
}
