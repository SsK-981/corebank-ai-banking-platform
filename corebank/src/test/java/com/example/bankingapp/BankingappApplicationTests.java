package com.example.bankingapp;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.CreateAccountRequest;
import com.example.bankingapp.dto.MoneyRequest;
import com.example.bankingapp.dto.KycUpdateRequest;
import com.example.bankingapp.dto.RegisterRequest;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.TransferRequest;
import com.example.bankingapp.exception.AccessDeniedBusinessException;
import com.example.bankingapp.exception.InsufficientBalanceException;
import com.example.bankingapp.exception.InvalidTransactionException;
import com.example.bankingapp.model.KycStatus;
import com.example.bankingapp.model.TransactionStatus;
import com.example.bankingapp.service.AccountService;
import com.example.bankingapp.service.AuthService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BankingappApplicationTests {

    @Autowired
    private AccountService accountService;

    @Autowired
    private AuthService authService;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void contextLoads() {
    }

    @Test
    void unauthenticatedAccountRequestsAreRejected() throws Exception {
        mockMvc.perform(get("/customer/accounts"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void registeredUserCanCreateAccountThroughApi() throws Exception {
        String email = registerCustomer();

        mockMvc.perform(post("/customer/accounts")
                        .with(httpBasic(email, "password123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"holderName\":\"API User\",\"initialBalance\":1500.00}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.holderName").value("API User"))
                .andExpect(jsonPath("$.ownerEmail").value(email));
    }

    @Test
    void transferPreviewOnlyReturnsAMaskedNameForAnEligibleRecipient() throws Exception {
        String senderEmail = registerCustomer();
        String recipientEmail = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Portal Sender", BigDecimal.ZERO), senderEmail);
        AccountResponse recipient = accountService.createAccount(
                new CreateAccountRequest("Neha Patil", BigDecimal.ZERO), recipientEmail);
        String endpoint = "/customer/accounts/" + sender.accountId() + "/transfer-recipient";

        mockMvc.perform(get(endpoint).param("accountNumber", recipient.accountNumber()))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get(endpoint).param("accountNumber", recipient.accountNumber())
                        .with(httpBasic(recipientEmail, "password123")))
                .andExpect(status().isForbidden());
        mockMvc.perform(get(endpoint).param("accountNumber", sender.accountNumber())
                        .with(httpBasic(senderEmail, "password123")))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get(endpoint).param("accountNumber", recipient.accountNumber())
                        .with(httpBasic(senderEmail, "password123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.maskedName").value("Neha P•••"))
                .andExpect(jsonPath("$.length()").value(1));

        accountService.closeAccount(recipient.accountId(), recipientEmail, false);
        mockMvc.perform(get(endpoint).param("accountNumber", recipient.accountNumber())
                        .with(httpBasic(senderEmail, "password123")))
                .andExpect(status().isNotFound());
    }

    @Test
    void customerCannotAccessAdminEndpoints() throws Exception {
        String email = registerCustomer();

        mockMvc.perform(get("/admin/accounts")
                        .with(httpBasic(email, "password123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCannotAccessCustomerEndpoints() throws Exception {
        String email = registerAdmin();

        mockMvc.perform(get("/customer/accounts")
                        .with(httpBasic(email, "password123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void customerCannotUseLegacyMixedAccountEndpoint() throws Exception {
        String email = registerCustomer();

        mockMvc.perform(post("/accounts/create")
                        .with(httpBasic(email, "password123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"holderName\":\"Legacy User\",\"initialBalance\":1500.00}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void createsAccountWithOpeningDepositTransaction() {
        String user = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Priya Mehta", new BigDecimal("2500.00")),
                user
        );

        assertTrue(account.accountNumber().length() == 12);
        assertEquals(user, account.ownerEmail());
        assertEquals(0, new BigDecimal("2500.00").compareTo(account.balance()));
        assertEquals(1, accountService.getTransactions(account.accountId(), PageRequest.of(0, 10), user, false).getTotalElements());
    }

    @Test
    void customerCanCreateOnlyOneAccount() {
        String user = registerCustomer();
        accountService.createAccount(
                new CreateAccountRequest("First Account", new BigDecimal("1000.00")),
                user
        );

        assertThrows(InvalidTransactionException.class,
                () -> accountService.createAccount(
                        new CreateAccountRequest("Second Account", new BigDecimal("500.00")),
                        user
                ));
    }

    @Test
    void depositAndWithdrawUpdateBalance() {
        String user = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Kabir Rao", new BigDecimal("1000.00")),
                user
        );

        account = accountService.deposit(account.accountId(), new MoneyRequest(new BigDecimal("500.00")), user, false);
        account = accountService.withdraw(account.accountId(), new MoneyRequest(new BigDecimal("125.50")), user, false);

        assertEquals(0, new BigDecimal("1374.50").compareTo(account.balance()));
    }

    @Test
    void rejectsInvalidWithdrawals() {
        String user = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Neha Singh", new BigDecimal("300.00")),
                user
        );

        assertThrows(InsufficientBalanceException.class,
                () -> accountService.withdraw(account.accountId(), new MoneyRequest(new BigDecimal("301.00")), user, false));
        assertThrows(InvalidTransactionException.class,
                () -> accountService.deposit(account.accountId(), new MoneyRequest(BigDecimal.ZERO), user, false));
    }

    @Test
    void failedWithdrawalIsPersistedForSupportAndRiskReview() {
        String user = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Failed Attempt", new BigDecimal("300.00")),
                user
        );

        assertThrows(InsufficientBalanceException.class,
                () -> accountService.withdraw(
                        account.accountId(),
                        new MoneyRequest(new BigDecimal("500.00")),
                        user,
                        false
                ));

        var transactions = accountService.getTransactions(
                account.accountId(), PageRequest.of(0, 10), user, false
        );
        assertTrue(transactions.stream().anyMatch(transaction ->
                transaction.status() == TransactionStatus.FAILED
                        && "Insufficient balance".equals(transaction.failureReason())
        ));
    }

    @Test
    void serviceCredentialCanReadCustomerDataWithoutCustomerPassword() throws Exception {
        String email = registerCustomer();
        authService.updateKyc(email, new KycUpdateRequest(KycStatus.VERIFIED));

        mockMvc.perform(get("/internal/ai/customers/{email}/profile", email)
                        .header("X-CoreBank-Service-Token",
                                "test-corebank-service-token-at-least-32-characters"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value(email))
                .andExpect(jsonPath("$.kycStatus").value("VERIFIED"));

        mockMvc.perform(get("/internal/ai/customers/{email}/profile", email))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanUpdateCustomerKyc() throws Exception {
        String customer = registerCustomer();
        String admin = registerAdmin();

        mockMvc.perform(patch("/admin/customers/{email}/kyc", customer)
                        .with(httpBasic(admin, "password123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"VERIFIED\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.kycStatus").value("VERIFIED"));
    }

    @Test
    void concurrentWithdrawalsCannotOverspendAccount() throws Exception {
        String user = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Concurrent Account", new BigDecimal("100.00")),
                user
        );
        var ready = new CountDownLatch(2);
        var start = new CountDownLatch(1);
        var successes = new AtomicInteger();
        var executor = Executors.newFixedThreadPool(2);
        try {
            for (int index = 0; index < 2; index++) {
                executor.submit(() -> {
                    ready.countDown();
                    try {
                        start.await(5, TimeUnit.SECONDS);
                        accountService.withdraw(
                                account.accountId(),
                                new MoneyRequest(new BigDecimal("80.00")),
                                user,
                                false
                        );
                        successes.incrementAndGet();
                    } catch (RuntimeException ignored) {
                        // An optimistic-lock conflict or insufficient balance is expected.
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    }
                });
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();
            executor.shutdown();
            assertTrue(executor.awaitTermination(10, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }

        AccountResponse updated = accountService.getAccount(account.accountId(), user, false);
        assertEquals(1, successes.get());
        assertEquals(0, new BigDecimal("20.00").compareTo(updated.balance()));
    }

    @Test
    void transfersMoneyBetweenAccountsById() {
        String senderUser = registerCustomer();
        String receiverUser = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Sender Account", new BigDecimal("1000.00")),
                senderUser
        );
        AccountResponse receiver = accountService.createAccount(
                new CreateAccountRequest("Receiver Account", new BigDecimal("250.00")),
                receiverUser
        );

        accountService.transfer(new TransferRequest(
                sender.accountId(),
                receiver.accountId(),
                null,
                new BigDecimal("200.00")
        ), senderUser, false);

        AccountResponse updatedSender = accountService.getAccount(sender.accountId(), senderUser, false);
        AccountResponse updatedReceiver = accountService.getAccount(receiver.accountId(), receiverUser, false);

        assertEquals(0, new BigDecimal("800.00").compareTo(updatedSender.balance()));
        assertEquals(0, new BigDecimal("450.00").compareTo(updatedReceiver.balance()));
    }

    @Test
    void transfersMoneyUsingDestinationAccountNumber() {
        String senderUser = registerCustomer();
        String receiverUser = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Number Sender", new BigDecimal("900.00")),
                senderUser
        );
        AccountResponse receiver = accountService.createAccount(
                new CreateAccountRequest("Number Receiver", new BigDecimal("100.00")),
                receiverUser
        );

        accountService.transfer(new TransferRequest(
                sender.accountId(),
                null,
                receiver.accountNumber(),
                new BigDecimal("300.00")
        ), senderUser, false);

        AccountResponse updatedSender = accountService.getAccount(sender.accountId(), senderUser, false);
        AccountResponse updatedReceiver = accountService.getAccount(receiver.accountId(), receiverUser, false);

        assertEquals(0, new BigDecimal("600.00").compareTo(updatedSender.balance()));
        assertEquals(0, new BigDecimal("400.00").compareTo(updatedReceiver.balance()));
    }

    @Test
    void customersCannotAccessAccountsOwnedByOtherUsers() {
        String owner = registerCustomer();
        String otherUser = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Private Account", new BigDecimal("700.00")),
                owner
        );

        assertThrows(AccessDeniedBusinessException.class,
                () -> accountService.getAccount(account.accountId(), otherUser, false));
    }

    @Test
    void closesOnlyZeroBalanceAccounts() {
        String user = registerCustomer();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Close Me", BigDecimal.ZERO),
                user
        );

        AccountResponse closed = accountService.closeAccount(account.accountId(), user, false);

        assertFalse(closed.active());
    }

    @Test
    void riskInsightsFlagRepeatedOutboundActivity() {
        String senderUser = registerCustomer();
        String receiverUser = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Risk Sender", new BigDecimal("1000.00")),
                senderUser
        );
        AccountResponse receiver = accountService.createAccount(
                new CreateAccountRequest("Risk Receiver", new BigDecimal("100.00")),
                receiverUser
        );

        accountService.transfer(new TransferRequest(sender.accountId(), receiver.accountId(), null, new BigDecimal("200.00")), senderUser, false);
        accountService.transfer(new TransferRequest(sender.accountId(), receiver.accountId(), null, new BigDecimal("150.00")), senderUser, false);
        accountService.transfer(new TransferRequest(sender.accountId(), receiver.accountId(), null, new BigDecimal("125.00")), senderUser, false);

        RiskInsightResponse insight = accountService.getRiskInsights(sender.accountId(), senderUser, false);

        assertTrue(insight.riskScore() >= 35);
        assertEquals("MEDIUM", insight.riskLevel());
        assertTrue(insight.signals().stream().anyMatch(signal -> signal.code().equals("TRANSFER_VELOCITY")));
    }

    private String registerCustomer() {
        String email = "user-" + UUID.randomUUID() + "@example.com";
        authService.registerCustomer(new RegisterRequest("Test User", email, "password123", null));
        return email;
    }

    private String registerAdmin() {
        String email = "admin-" + UUID.randomUUID() + "@example.com";
        authService.registerAdmin(new RegisterRequest("Admin User", email, "password123", "admin123"));
        return email;
    }
}
