package com.example.bankingapp.dto;

import java.math.BigDecimal;

public record AccountResponse(
        Long accountId,
        String accountNumber,
        String holderName,
        BigDecimal balance,
        boolean active,
        String ownerEmail
) {
}
