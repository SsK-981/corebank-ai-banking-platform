package com.example.bankingapp.controller;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.AdminSummaryResponse;
import com.example.bankingapp.dto.AdminTransactionResponse;
import com.example.bankingapp.dto.MoneyRequest;
import com.example.bankingapp.dto.KycUpdateRequest;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.TransactionResponse;
import com.example.bankingapp.dto.UpdateAccountRequest;
import com.example.bankingapp.dto.UserResponse;
import com.example.bankingapp.service.AccountService;
import com.example.bankingapp.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/admin")
public class AdminPortalController {

    private final AccountService accountService;
    private final AuthService authService;

    public AdminPortalController(AccountService accountService, AuthService authService) {
        this.accountService = accountService;
        this.authService = authService;
    }

    @GetMapping("/summary")
    public AdminSummaryResponse getSummary() {
        return accountService.getAdminSummary();
    }

    @GetMapping("/customers")
    public Page<UserResponse> getCustomers(Pageable pageable) {
        return authService.getCustomers(pageable);
    }

    @PatchMapping("/customers/{email}/kyc")
    public UserResponse updateKyc(@PathVariable String email,
                                  @Valid @RequestBody KycUpdateRequest request) {
        return authService.updateKyc(email, request);
    }

    @GetMapping("/accounts")
    public Page<AccountResponse> getAccounts(@RequestParam(required = false) String query, Pageable pageable) {
        return accountService.searchAccounts(query, pageable);
    }

    @GetMapping("/accounts/{accountId}")
    public AccountResponse getAccount(@PathVariable Long accountId) {
        return accountService.getAccount(accountId, "admin", true);
    }

    @PutMapping("/accounts/{accountId}")
    public AccountResponse updateAccount(@PathVariable Long accountId,
                                         @Valid @RequestBody UpdateAccountRequest request) {
        return accountService.updateAccount(accountId, request, "admin", true);
    }

    @DeleteMapping("/accounts/{accountId}")
    public AccountResponse closeAccount(@PathVariable Long accountId) {
        return accountService.closeAccount(accountId, "admin", true);
    }

    @PostMapping("/accounts/{accountId}/credit")
    public AccountResponse creditAccount(@PathVariable Long accountId,
                                         @Valid @RequestBody MoneyRequest request) {
        return accountService.deposit(accountId, request, "admin", true);
    }

    @GetMapping("/accounts/{accountId}/transactions")
    public Page<TransactionResponse> getAccountTransactions(@PathVariable Long accountId, Pageable pageable) {
        return accountService.getTransactions(accountId, pageable, "admin", true);
    }

    @GetMapping("/accounts/{accountId}/risk-insights")
    public RiskInsightResponse getRiskInsights(@PathVariable Long accountId) {
        return accountService.getRiskInsights(accountId, "admin", true);
    }

    @GetMapping("/accounts/{accountId}/statement.csv")
    public ResponseEntity<String> exportStatement(@PathVariable Long accountId) {
        String filename = "account-" + accountId + "-statement.csv";
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/csv"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .body(accountService.exportStatementCsv(accountId, "admin", true));
    }

    @GetMapping("/accounts.csv")
    public ResponseEntity<String> exportAccounts() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/csv"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"accounts.csv\"")
                .body(accountService.exportAccountsCsv());
    }

    @GetMapping("/transactions")
    public Page<AdminTransactionResponse> getTransactions(Pageable pageable) {
        return accountService.getAllTransactions(pageable);
    }

    @GetMapping("/transactions.csv")
    public ResponseEntity<String> exportTransactions() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/csv"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"transactions.csv\"")
                .body(accountService.exportTransactionsCsv());
    }
}
