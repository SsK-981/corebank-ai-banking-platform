package com.example.bankingapp.dto;

public record RiskSignalResponse(
        String code,
        String title,
        String detail,
        int points
) {
}
