package com.example.bankingapp.controller;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.TransactionResponse;
import com.example.bankingapp.dto.UserResponse;
import com.example.bankingapp.service.AccountService;
import com.example.bankingapp.service.AuthService;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/ai/customers/{email}")
public class InternalAiController {

    private final AccountService accountService;
    private final AuthService authService;

    public InternalAiController(AccountService accountService, AuthService authService) {
        this.accountService = accountService;
        this.authService = authService;
    }

    @GetMapping("/profile")
    public UserResponse profile(@PathVariable String email) {
        return authService.getCurrentUser(email);
    }

    @GetMapping("/accounts")
    public Page<AccountResponse> accounts(@PathVariable String email, Pageable pageable) {
        return accountService.getAccounts(pageable, email, false);
    }

    @GetMapping("/accounts/{accountId}/transactions")
    public Page<TransactionResponse> transactions(@PathVariable String email,
                                                  @PathVariable Long accountId,
                                                  Pageable pageable) {
        return accountService.getTransactions(accountId, pageable, email, false);
    }

    @GetMapping("/accounts/{accountId}/risk-insights")
    public RiskInsightResponse riskInsights(@PathVariable String email,
                                            @PathVariable Long accountId) {
        return accountService.getRiskInsights(accountId, email, false);
    }
}
