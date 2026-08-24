package com.diploma.idsml.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank(message = "Perdoruesi eshte i detyrueshem.")
        @Size(min = 3, max = 50, message = "Perdoruesi duhet te kete 3-50 karaktere.")
        @Pattern(regexp = "^[A-Za-z0-9._-]+$",
                message = "Perdoruesi lejon vetem shkronja, numra, pike, vize dhe nenvize.")
        String username,

        @NotBlank(message = "Fjalekalimi eshte i detyrueshem.")
        @Size(min = 8, max = 100, message = "Fjalekalimi duhet te kete te pakten 8 karaktere.")
        @Pattern(regexp = "^(?=.*[A-Za-z])(?=.*\\d).+$",
                message = "Fjalekalimi duhet te permbaje te pakten nje shkronje dhe nje numer.")
        String password,

        @NotBlank(message = "Konfirmimi i fjalekalimit eshte i detyrueshem.")
        String confirmPassword
) {
}
