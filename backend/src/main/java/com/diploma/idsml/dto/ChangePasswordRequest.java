package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ChangePasswordRequest(
        @NotBlank(message = "Fjalekalimi aktual eshte i detyrueshem.")
        String currentPassword,

        @NotBlank(message = "Fjalekalimi i ri eshte i detyrueshem.")
        @Size(min = 8, max = 100, message = "Fjalekalimi duhet te kete te pakten 8 karaktere.")
        @Pattern(regexp = "^(?=.*[A-Za-z])(?=.*\\d).+$",
                message = "Fjalekalimi duhet te permbaje te pakten nje shkronje dhe nje numer.")
        String newPassword,

        @NotBlank(message = "Konfirmimi i fjalekalimit eshte i detyrueshem.")
        String confirmPassword
) {
}
