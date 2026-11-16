package com.example.bankingapp.dto;

public record CustomerTransferResponse(
        AccountResponse fromAccount,
        TransferRecipientResponse toAccount,
        String referenceNumber
) {
}
