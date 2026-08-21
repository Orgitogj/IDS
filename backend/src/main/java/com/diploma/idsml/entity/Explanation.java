package com.diploma.idsml.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "explanations")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Explanation {

    @Id
    @Builder.Default
    private UUID id = UUID.randomUUID();

    @OneToOne
    @JoinColumn(name = "alarm_id", nullable = false, unique = true)
    private Alarm alarm;

    @Column(name = "explanation_text", columnDefinition = "TEXT", nullable = false)
    private String explanationText;

    @Column(name = "llm_model", nullable = false)
    private String llmModel;

    @Column(name = "llm_prompt_version", nullable = false)
    private String llmPromptVersion;

    @Column(name = "generated_at", nullable = false, updatable = false)
    @Builder.Default
    private Instant generatedAt = Instant.now();
}
