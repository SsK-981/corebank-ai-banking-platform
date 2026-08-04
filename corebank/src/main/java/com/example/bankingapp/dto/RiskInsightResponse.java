package com.example.bankingapp.dto;

import java.math.BigDecimal;
import java.util.List;

public record RiskInsightResponse(
        Long accountId,
        String accountNumber,
        String riskLevel,
        int riskScore,
        BigDecimal currentBalance,
        BigDecimal totalCredits,
        BigDecimal totalDebits,
        BigDecimal largestTransaction,
        long transactionCount,
        List<RiskSignalResponse> signals,
        String recommendation
) {
}
