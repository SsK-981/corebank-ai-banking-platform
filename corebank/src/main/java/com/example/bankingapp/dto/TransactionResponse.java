package com.example.bankingapp.dto;

import com.example.bankingapp.model.TransactionStatus;
import com.example.bankingapp.model.TransactionType;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public record TransactionResponse(
        Long id,
        TransactionType type,
        BigDecimal amount,
        LocalDateTime timestamp,
        String referenceNumber,
        String description,
        TransactionStatus status,
        String failureReason
) {
}
