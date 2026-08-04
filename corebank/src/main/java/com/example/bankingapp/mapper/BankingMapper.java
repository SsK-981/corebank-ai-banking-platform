package com.example.bankingapp.mapper;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.TransactionResponse;
import com.example.bankingapp.model.BankAccount;
import com.example.bankingapp.model.Transaction;

public final class BankingMapper {
    private BankingMapper() {
    }

    public static AccountResponse toAccountResponse(BankAccount account) {
        return new AccountResponse(
                account.getAccountId(),
                account.getAccountNumber(),
                account.getHolderName(),
                account.getBalance(),
                account.isActive(),
                account.getOwner().getEmail()
        );
    }

    public static TransactionResponse toTransactionResponse(Transaction transaction) {
        return new TransactionResponse(
                transaction.getId(),
                transaction.getType(),
                transaction.getAmount(),
                transaction.getTimestamp(),
                transaction.getReferenceNumber(),
                transaction.getDescription(),
                transaction.getStatus(),
                transaction.getFailureReason()
        );
    }
}
