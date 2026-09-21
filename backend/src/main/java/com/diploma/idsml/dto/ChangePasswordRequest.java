package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ChangePasswordRequest(
        @NotBlank(message = "Fjalëkalimi aktual është i detyrueshëm.")
        String currentPassword,

        @NotBlank(message = "Fjalëkalimi i ri është i detyrueshëm.")
        @Size(min = 8, max = 100, message = "Fjalëkalimi duhet të ketë të paktën 8 karaktere.")
        @Pattern(regexp = "^(?=.*[A-Za-z])(?=.*\\d).+$",
                message = "Fjalëkalimi duhet të përmbajë të paktën një shkronjë dhe një numër.")
        String newPassword,

        @NotBlank(message = "Konfirmimi i fjalëkalimit është i detyrueshëm.")
        String confirmPassword
) {
}
