package com.example.bankingapp.service;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.AdminTransactionResponse;
import com.example.bankingapp.dto.AdminSummaryResponse;
import com.example.bankingapp.dto.CreateAccountRequest;
import com.example.bankingapp.dto.CustomerTransferResponse;
import com.example.bankingapp.dto.MoneyRequest;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.TransactionResponse;
import com.example.bankingapp.dto.TransferRecipientResponse;
import com.example.bankingapp.dto.TransferRequest;
import com.example.bankingapp.dto.TransferResponse;
import com.example.bankingapp.dto.UpdateAccountRequest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface AccountService {

    AccountResponse createAccount(CreateAccountRequest request, String username);

    AccountResponse getAccount(Long accountId, String username, boolean admin);

    AccountResponse getAccountByNumber(String accountNumber, String username, boolean admin);

    Page<AccountResponse> getAccounts(Pageable pageable, String username, boolean admin);

    Page<AccountResponse> searchAccounts(String query, Pageable pageable);

    AccountResponse updateAccount(Long accountId, UpdateAccountRequest request, String username, boolean admin);

    AccountResponse closeAccount(Long accountId, String username, boolean admin);

    AccountResponse deposit(Long accountId, MoneyRequest request, String username, boolean admin);

    AccountResponse withdraw(Long accountId, MoneyRequest request, String username, boolean admin);

    TransferRecipientResponse previewTransferRecipient(Long sourceAccountId, String accountNumber, String username);

    TransferResponse transfer(TransferRequest request, String username, boolean admin);

    CustomerTransferResponse transferCustomer(TransferRequest request, String username, String idempotencyKey);

    Page<TransactionResponse> getTransactions(Long accountId, Pageable pageable, String username, boolean admin);

    Page<AdminTransactionResponse> getAllTransactions(Pageable pageable);

    String exportStatementCsv(Long accountId, String username, boolean admin);

    String exportAccountsCsv();

    String exportTransactionsCsv();

    AdminSummaryResponse getAdminSummary();

    RiskInsightResponse getRiskInsights(Long accountId, String username, boolean admin);
}
