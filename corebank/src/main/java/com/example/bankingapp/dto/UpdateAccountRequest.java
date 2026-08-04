package com.example.bankingapp.dto;

import jakarta.validation.constraints.NotBlank;

public record UpdateAccountRequest(
        @NotBlank(message = "Account holder name is required")
        String holderName
) {
}
