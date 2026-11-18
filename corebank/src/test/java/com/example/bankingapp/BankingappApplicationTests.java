package com.example.bankingapp;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.CreateAccountRequest;
import com.example.bankingapp.dto.MoneyRequest;
import com.example.bankingapp.dto.KycUpdateRequest;
import com.example.bankingapp.dto.RegisterRequest;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.TransferRequest;
import com.jayway.jsonpath.JsonPath;
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
import org.springframework.test.web.servlet.MvcResult;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Future;
import java.util.function.IntFunction;
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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
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
    void concurrentDistinctTransfersUseTheLatestAvailableBalance() throws Exception {
        String senderEmail = registerCustomer();
        String receiverEmail = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Concurrent Sender", new BigDecimal("5000.00")), senderEmail);
        AccountResponse receiver = accountService.createAccount(
                new CreateAccountRequest("Concurrent Recipient", BigDecimal.ZERO), receiverEmail);
        String body = transferBody(sender, receiver, "400.00");

        List<MvcResult> results = concurrentTransfers(
                senderEmail, body, index -> UUID.randomUUID().toString());

        assertEquals(12, results.stream().filter(result -> result.getResponse().getStatus() == 200).count());
        assertEquals(8, results.stream().filter(result -> result.getResponse().getStatus() == 400).count());
        for (MvcResult result : results) {
            if (result.getResponse().getStatus() == 400) {
                String reason = JsonPath.read(result.getResponse().getContentAsString(), "$.messages[0]");
                assertEquals("Insufficient balance for transfer", reason);
            }
        }
        assertEquals(new BigDecimal("200.00"), accountService.getAccount(sender.accountId(), senderEmail, false).balance());
        assertEquals(new BigDecimal("4800.00"), accountService.getAccount(receiver.accountId(), receiverEmail, false).balance());
    }

    @Test
    void concurrentRetriesReturnTheOriginalReceiptAndPostOnce() throws Exception {
        String senderEmail = registerCustomer();
        String receiverEmail = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Retry Sender", new BigDecimal("5000.00")), senderEmail);
        AccountResponse receiver = accountService.createAccount(
                new CreateAccountRequest("Retry Recipient", BigDecimal.ZERO), receiverEmail);
        String key = UUID.randomUUID().toString();

        List<MvcResult> results = concurrentTransfers(
                senderEmail, transferBody(sender, receiver, "400.00"), index -> key);

        String originalReceipt = results.getFirst().getResponse().getContentAsString();
        for (MvcResult result : results) {
            assertEquals(200, result.getResponse().getStatus());
            assertEquals(originalReceipt, result.getResponse().getContentAsString());
        }
        assertEquals(1, (int) JsonPath.read(originalReceipt, "$.toAccount.length()"));
        String name = JsonPath.read(originalReceipt, "$.toAccount.maskedName");
        assertTrue(name.startsWith("Retry R"));
        assertEquals(new BigDecimal("4600.00"), accountService.getAccount(sender.accountId(), senderEmail, false).balance());
        assertEquals(new BigDecimal("400.00"), accountService.getAccount(receiver.accountId(), receiverEmail, false).balance());

        mockMvc.perform(post("/customer/accounts/transfer")
                        .with(httpBasic(senderEmail, "password123"))
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transferBody(sender, receiver, "401.00")))
                .andExpect(status().isConflict());
        assertEquals(new BigDecimal("4600.00"), accountService.getAccount(sender.accountId(), senderEmail, false).balance());
    }

    @Test
    void insufficientFundsReplayKeepsTheOriginalDeclineAfterATopUp() throws Exception {
        String senderEmail = registerCustomer();
        String receiverEmail = registerCustomer();
        AccountResponse sender = accountService.createAccount(
                new CreateAccountRequest("Declined Sender", BigDecimal.ZERO), senderEmail);
        AccountResponse receiver = accountService.createAccount(
                new CreateAccountRequest("Declined Recipient", BigDecimal.ZERO), receiverEmail);
        String key = UUID.randomUUID().toString();
        String body = transferBody(sender, receiver, "400.00");

        mockMvc.perform(post("/customer/accounts/transfer")
                        .with(httpBasic(senderEmail, "password123"))
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.messages[0]").value("Insufficient balance for transfer"));

        accountService.deposit(sender.accountId(), new MoneyRequest(new BigDecimal("500.00")), senderEmail, false);

        mockMvc.perform(post("/customer/accounts/transfer")
                        .with(httpBasic(senderEmail, "password123"))
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.messages[0]").value("Insufficient balance for transfer"));
        assertEquals(new BigDecimal("500.00"), accountService.getAccount(sender.accountId(), senderEmail, false).balance());
        assertEquals(new BigDecimal("0.00"), accountService.getAccount(receiver.accountId(), receiverEmail, false).balance());
        var history = accountService.getTransactions(sender.accountId(), PageRequest.of(0, 10), senderEmail, false);
        assertEquals(1, history.stream().filter(row -> row.status() == TransactionStatus.FAILED).count());

        mockMvc.perform(post("/customer/accounts/transfer")
                        .with(httpBasic(senderEmail, "password123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transferBody(sender, receiver, "600.00")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.messages[0]").value("Insufficient balance for transfer"));

    }

    private List<MvcResult> concurrentTransfers(String email, String body, IntFunction<String> getKey)
            throws Exception {
        int count = 20;
        var ready = new CountDownLatch(count);
        var start = new CountDownLatch(1);
        var futures = new ArrayList<Future<MvcResult>>(count);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int index = 0; index < count; index++) {
                String key = getKey.apply(index);
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Transfer start timed out");
                    }
                    return mockMvc.perform(post("/customer/accounts/transfer")
                                    .with(httpBasic(email, "password123"))
                                    .header("Idempotency-Key", key)
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(body))
                            .andReturn();
                }));
            }
            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();
            var results = new ArrayList<MvcResult>(count);
            for (var future : futures) {
                results.add(future.get(30, TimeUnit.SECONDS));
            }
            return results;
        }
    }

    private String transferBody(AccountResponse sender, AccountResponse receiver, String amount) {
        return """
                {"fromAccountId":%d,"toAccountNumber":"%s","amount":%s}
                """.formatted(sender.accountId(), receiver.accountNumber(), amount);
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

    @Test
    void customerCannotRenameAccountAndAdminCanCorrectIt() throws Exception {
        String customer = registerCustomer();
        String admin = registerAdmin();
        AccountResponse account = accountService.createAccount(
                new CreateAccountRequest("Original Name", new BigDecimal("1500.00")), customer);

        mockMvc.perform(put("/customer/accounts/{id}", account.accountId())
                        .with(httpBasic(customer, "password123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"holderName\":\"Changed Name\"}"))
                .andExpect(status().isForbidden());
        assertEquals("Original Name",
                accountService.getAccount(account.accountId(), customer, false).holderName());

        mockMvc.perform(put("/admin/accounts/{id}", account.accountId())
                        .with(httpBasic(admin, "password123"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"holderName\":\"Corrected Name\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.holderName").value("Corrected Name"));
        AccountResponse corrected = accountService.getAccount(account.accountId(), customer, false);
        assertEquals("Corrected Name", corrected.holderName());
        assertEquals(account.accountNumber(), corrected.accountNumber());
        assertEquals(0, account.balance().compareTo(corrected.balance()));
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
