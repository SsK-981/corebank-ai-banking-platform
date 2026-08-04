package com.example.bankingapp.dto;

import com.example.bankingapp.model.KycStatus;
import com.example.bankingapp.model.Role;

public record UserResponse(
        Long id,
        String fullName,
        String email,
        Role role,
        KycStatus kycStatus
) {
}
