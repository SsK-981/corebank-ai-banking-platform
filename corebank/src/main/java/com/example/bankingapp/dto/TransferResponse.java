package com.example.bankingapp.dto;

public record TransferResponse(
        AccountResponse fromAccount,
        AccountResponse toAccount,
        String referenceNumber
) {
}
