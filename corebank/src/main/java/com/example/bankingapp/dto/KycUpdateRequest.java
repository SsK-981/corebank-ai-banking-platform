package com.example.bankingapp.dto;

import com.example.bankingapp.model.KycStatus;
import jakarta.validation.constraints.NotNull;

public record KycUpdateRequest(
        @NotNull(message = "KYC status is required")
        KycStatus status
) {
}
