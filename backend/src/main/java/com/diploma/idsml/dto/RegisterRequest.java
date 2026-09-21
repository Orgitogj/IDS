package com.diploma.idsml.dto;

import com.diploma.idsml.entity.UserRole;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank(message = "Përdoruesi është i detyrueshëm.")
        @Size(min = 3, max = 50, message = "Përdoruesi duhet të ketë 3–50 karaktere.")
        @Pattern(regexp = "^[A-Za-z0-9._-]+$",
                message = "Përdoruesi mund të përmbajë vetëm shkronja, numra, pika, viza dhe nënviza.")
        String username,

        @NotBlank(message = "Fjalëkalimi është i detyrueshëm.")
        @Size(min = 8, max = 100, message = "Fjalëkalimi duhet të ketë të paktën 8 karaktere.")
        @Pattern(regexp = "^(?=.*[A-Za-z])(?=.*\\d).+$",
                message = "Fjalëkalimi duhet të përmbajë të paktën një shkronjë dhe një numër.")
        String password,

        @NotBlank(message = "Konfirmimi i fjalëkalimit është i detyrueshëm.")
        String confirmPassword,

        @NotNull(message = "Roli është i detyrueshëm.")
        UserRole role
) {
}
