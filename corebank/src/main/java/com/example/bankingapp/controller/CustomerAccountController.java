package com.example.bankingapp.controller;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.CreateAccountRequest;
import com.example.bankingapp.dto.MoneyRequest;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.TransactionResponse;
import com.example.bankingapp.dto.TransferRecipientResponse;
import com.example.bankingapp.dto.TransferRequest;
import com.example.bankingapp.dto.TransferResponse;
import com.example.bankingapp.dto.UpdateAccountRequest;
import com.example.bankingapp.service.AccountService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/customer/accounts")
public class CustomerAccountController {

    private final AccountService accountService;

    public CustomerAccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @PostMapping
    public AccountResponse createAccount(@Valid @RequestBody CreateAccountRequest request,
                                         Authentication authentication) {
        return accountService.createAccount(request, authentication.getName());
    }

    @GetMapping
    public Page<AccountResponse> getAccounts(Pageable pageable, Authentication authentication) {
        return accountService.getAccounts(pageable, authentication.getName(), false);
    }

    @GetMapping("/{accountId}")
    public AccountResponse getAccount(@PathVariable Long accountId, Authentication authentication) {
        return accountService.getAccount(accountId, authentication.getName(), false);
    }

    @PutMapping("/{accountId}")
    public AccountResponse updateAccount(@PathVariable Long accountId,
                                         @Valid @RequestBody UpdateAccountRequest request,
                                         Authentication authentication) {
        return accountService.updateAccount(accountId, request, authentication.getName(), false);
    }

    @DeleteMapping("/{accountId}")
    public AccountResponse closeAccount(@PathVariable Long accountId, Authentication authentication) {
        return accountService.closeAccount(accountId, authentication.getName(), false);
    }

    @PostMapping("/{accountId}/withdraw")
    public AccountResponse withdraw(@PathVariable Long accountId,
                                    @Valid @RequestBody MoneyRequest request,
                                    Authentication authentication) {
        return accountService.withdraw(accountId, request, authentication.getName(), false);
    }

    @GetMapping("/{accountId}/transfer-recipient")
    public ResponseEntity<TransferRecipientResponse> previewTransferRecipient(
            @PathVariable Long accountId, @RequestParam String accountNumber, Authentication authentication) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(accountService.previewTransferRecipient(accountId, accountNumber, authentication.getName()));
    }

    @PostMapping("/transfer")
    public TransferResponse transfer(@Valid @RequestBody TransferRequest request,
                                     Authentication authentication) {
        return accountService.transfer(request, authentication.getName(), false);
    }

    @GetMapping("/{accountId}/transactions")
    public Page<TransactionResponse> getTransactions(@PathVariable Long accountId,
                                                    Pageable pageable,
                                                    Authentication authentication) {
        return accountService.getTransactions(accountId, pageable, authentication.getName(), false);
    }

    @GetMapping("/{accountId}/statement.csv")
    public ResponseEntity<String> exportStatement(@PathVariable Long accountId, Authentication authentication) {
        String filename = "account-" + accountId + "-statement.csv";
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/csv"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .body(accountService.exportStatementCsv(accountId, authentication.getName(), false));
    }

    @GetMapping("/{accountId}/risk-insights")
    public RiskInsightResponse getRiskInsights(@PathVariable Long accountId, Authentication authentication) {
        return accountService.getRiskInsights(accountId, authentication.getName(), false);
    }
}
