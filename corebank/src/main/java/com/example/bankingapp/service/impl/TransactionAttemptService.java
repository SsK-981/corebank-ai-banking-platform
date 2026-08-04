package com.example.bankingapp.service.impl;

import com.example.bankingapp.model.BankAccount;
import com.example.bankingapp.model.Transaction;
import com.example.bankingapp.model.TransactionStatus;
import com.example.bankingapp.model.TransactionType;
import com.example.bankingapp.repository.BankAccountRepository;
import com.example.bankingapp.repository.TransactionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.UUID;

@Service
public class TransactionAttemptService {

    private final BankAccountRepository bankAccountRepository;
    private final TransactionRepository transactionRepository;

    public TransactionAttemptService(BankAccountRepository bankAccountRepository,
                                     TransactionRepository transactionRepository) {
        this.bankAccountRepository = bankAccountRepository;
        this.transactionRepository = transactionRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(Long accountId, TransactionType type, BigDecimal amount,
                              String failureReason) {
        BankAccount account = bankAccountRepository.findById(accountId).orElse(null);
        if (account == null) {
            return;
        }
        String reference = "FAIL" + UUID.randomUUID().toString().replace("-", "")
                .substring(0, 16).toUpperCase();
        Transaction transaction = new Transaction(
                type,
                amount,
                reference,
                "Failed " + type.name().toLowerCase().replace('_', ' '),
                TransactionStatus.FAILED,
                failureReason
        );
        transaction.setBankAccount(account);
        transactionRepository.save(transaction);
    }
}
