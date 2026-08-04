package com.example.bankingapp.dto;

import java.math.BigDecimal;

public record AdminSummaryResponse(
        long totalAccounts,
        long activeAccounts,
        long closedAccounts,
        long totalTransactions,
        BigDecimal totalBankBalance
) {
}
