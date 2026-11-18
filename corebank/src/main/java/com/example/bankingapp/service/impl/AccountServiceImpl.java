package com.example.bankingapp.service.impl;

import com.example.bankingapp.dto.AccountResponse;
import com.example.bankingapp.dto.AdminTransactionResponse;
import com.example.bankingapp.dto.AdminSummaryResponse;
import com.example.bankingapp.dto.CreateAccountRequest;
import com.example.bankingapp.dto.CustomerTransferResponse;
import com.example.bankingapp.dto.MoneyRequest;
import com.example.bankingapp.dto.RiskInsightResponse;
import com.example.bankingapp.dto.RiskSignalResponse;
import com.example.bankingapp.dto.TransactionResponse;
import com.example.bankingapp.dto.TransferRecipientResponse;
import com.example.bankingapp.dto.TransferRequest;
import com.example.bankingapp.dto.TransferResponse;
import com.example.bankingapp.dto.UpdateAccountRequest;
import com.example.bankingapp.exception.AccessDeniedBusinessException;
import com.example.bankingapp.exception.AccountClosedException;
import com.example.bankingapp.exception.AccountNotFoundException;
import com.example.bankingapp.exception.InsufficientBalanceException;
import com.example.bankingapp.exception.DuplicateResourceException;
import com.example.bankingapp.exception.InvalidTransactionException;
import com.example.bankingapp.mapper.BankingMapper;
import com.example.bankingapp.model.BankAccount;
import com.example.bankingapp.model.Transaction;
import com.example.bankingapp.model.TransferIdempotencyRecord;
import com.example.bankingapp.model.TransactionStatus;
import com.example.bankingapp.model.TransactionType;
import com.example.bankingapp.repository.BankAccountRepository;
import com.example.bankingapp.repository.TransactionRepository;
import com.example.bankingapp.repository.TransferIdempotencyRepository;
import com.example.bankingapp.service.AuthService;
import com.example.bankingapp.service.AccountService;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@Service
public class AccountServiceImpl implements AccountService {

    private final BankAccountRepository bankAccountRepository;
    private final TransactionRepository transactionRepository;
    private final AuthService authService;
    private final TransactionAttemptService transactionAttemptService;
    private final TransferIdempotencyRepository transferIdempotencyRepository;

    public AccountServiceImpl(BankAccountRepository bankAccountRepository,
                              TransactionRepository transactionRepository,
                              AuthService authService,
                              TransactionAttemptService transactionAttemptService,
                              TransferIdempotencyRepository transferIdempotencyRepository) {
        this.bankAccountRepository = bankAccountRepository;
        this.transactionRepository = transactionRepository;
        this.authService = authService;
        this.transactionAttemptService = transactionAttemptService;
        this.transferIdempotencyRepository = transferIdempotencyRepository;
    }

    @Override
    @Transactional
    public AccountResponse createAccount(CreateAccountRequest request, String username) {
        if (request.holderName() == null || request.holderName().isBlank()) {
            throw new InvalidTransactionException("Account holder name is required");
        }
        if (request.initialBalance() == null || request.initialBalance().compareTo(BigDecimal.ZERO) < 0) {
            throw new InvalidTransactionException("Initial balance cannot be negative");
        }
        if (bankAccountRepository.existsByOwnerEmailIgnoreCase(username)) {
            throw new InvalidTransactionException("This user already has a bank account");
        }

        BankAccount account = new BankAccount();
        account.setHolderName(request.holderName().trim());
        account.setBalance(request.initialBalance());
        account.setAccountNumber(generateAccountNumber());
        account.setOwner(authService.findUser(username));

        if (request.initialBalance().compareTo(BigDecimal.ZERO) > 0) {
            account.addTransaction(new Transaction(
                    TransactionType.OPENING_DEPOSIT,
                    request.initialBalance(),
                    generateReferenceNumber(),
                    "Initial account funding"
            ));
        }

        return BankingMapper.toAccountResponse(bankAccountRepository.save(account));
    }

    @Override
    @Transactional(readOnly = true)
    public AccountResponse getAccount(Long accountId, String username, boolean admin) {
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        return BankingMapper.toAccountResponse(account);
    }

    @Override
    @Transactional(readOnly = true)
    public AccountResponse getAccountByNumber(String accountNumber, String username, boolean admin) {
        BankAccount account = bankAccountRepository.findByAccountNumber(accountNumber)
                .orElseThrow(() -> new AccountNotFoundException("Account not found"));
        ensureOwnerOrAdmin(account, username, admin);
        return BankingMapper.toAccountResponse(account);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<AccountResponse> getAccounts(Pageable pageable, String username, boolean admin) {
        Page<BankAccount> accounts = admin
                ? bankAccountRepository.findAll(pageable)
                : bankAccountRepository.findByOwnerEmailIgnoreCase(username, pageable);

        return accounts
                .map(BankingMapper::toAccountResponse);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<AccountResponse> searchAccounts(String query, Pageable pageable) {
        String normalized = query == null ? "" : query.trim().toLowerCase(Locale.ROOT);
        List<AccountResponse> matches = bankAccountRepository.findAll()
                .stream()
                .filter(account -> normalized.isBlank() || accountMatches(account, normalized))
                .map(BankingMapper::toAccountResponse)
                .toList();

        int start = (int) Math.min(pageable.getOffset(), matches.size());
        int end = Math.min(start + pageable.getPageSize(), matches.size());
        return new PageImpl<>(matches.subList(start, end), pageable, matches.size());
    }

    @Override
    @Transactional
    public AccountResponse updateAccount(Long accountId, UpdateAccountRequest request, String username, boolean admin) {
        if (request.holderName() == null || request.holderName().isBlank()) {
            throw new InvalidTransactionException("Account holder name is required");
        }

        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        if (!admin) {
            throw new AccessDeniedBusinessException(
                    "Account holder names can only be corrected by a bank administrator");
        }
        account.setHolderName(request.holderName().trim());
        return BankingMapper.toAccountResponse(bankAccountRepository.save(account));
    }

    @Override
    @Transactional
    public AccountResponse closeAccount(Long accountId, String username, boolean admin) {
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        ensureActive(account);

        if (account.getBalance().compareTo(BigDecimal.ZERO) != 0) {
            throw new InvalidTransactionException("Only zero-balance accounts can be closed");
        }

        account.setActive(false);
        return BankingMapper.toAccountResponse(bankAccountRepository.save(account));
    }

    @Override
    @Transactional
    public AccountResponse deposit(Long accountId, MoneyRequest request, String username, boolean admin) {
        validatePositiveAmount(request.amount());
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        ensureActive(account);

        account.setBalance(account.getBalance().add(request.amount()));
        account.addTransaction(new Transaction(
                TransactionType.DEPOSIT,
                request.amount(),
                generateReferenceNumber(),
                "Cash deposit"
        ));

        return BankingMapper.toAccountResponse(bankAccountRepository.save(account));
    }

    @Override
    @Transactional
    public AccountResponse withdraw(Long accountId, MoneyRequest request, String username, boolean admin) {
        validatePositiveAmount(request.amount());
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        ensureActive(account);

        if (account.getBalance().compareTo(request.amount()) < 0) {
            transactionAttemptService.recordFailure(
                    account.getAccountId(),
                    TransactionType.WITHDRAW,
                    request.amount(),
                    "Insufficient balance"
            );
            throw new InsufficientBalanceException("Insufficient balance");
        }

        account.setBalance(account.getBalance().subtract(request.amount()));
        account.addTransaction(new Transaction(
                TransactionType.WITHDRAW,
                request.amount(),
                generateReferenceNumber(),
                "Cash withdrawal"
        ));

        return BankingMapper.toAccountResponse(bankAccountRepository.save(account));
    }

    @Override
    @Transactional(readOnly = true)
    public TransferRecipientResponse previewTransferRecipient(Long sourceAccountId, String accountNumber, String username) {
        BankAccount source = findAccount(sourceAccountId);
        ensureOwnerOrAdmin(source, username, false);
        ensureActive(source);

        if (!accountNumber.matches("[0-9]{12}")) {
            throw new InvalidTransactionException("Enter a valid 12-digit account number.");
        }
        if (source.getAccountNumber().equals(accountNumber)) {
            throw new InvalidTransactionException("The recipient account must be different from the source account.");
        }

        BankAccount recipient = bankAccountRepository.findByAccountNumber(accountNumber)
                .filter(BankAccount::isActive)
                .orElseThrow(() -> new AccountNotFoundException("No eligible recipient was found for this account number."));
        String[] names = recipient.getHolderName().strip().split("\\s+", 2);
        String surname = names.length == 2 ? names[1] : names[0];
        String initial = surname.substring(0, surname.offsetByCodePoints(0, 1));
        String maskedName = names.length == 2 ? names[0] + " " + initial + "•••" : initial + "•••";
        return new TransferRecipientResponse(maskedName);
    }

    @Override
    @Transactional(noRollbackFor = InsufficientBalanceException.class)
    public TransferResponse transfer(TransferRequest request, String username, boolean admin) {
        PostedTransfer posted = postTransfer(request, username, admin);
        return new TransferResponse(
                BankingMapper.toAccountResponse(posted.source()),
                BankingMapper.toAccountResponse(posted.destination()),
                posted.referenceNumber()
        );
    }

    @Override
    @Transactional(noRollbackFor = InsufficientBalanceException.class)
    public CustomerTransferResponse transferCustomer(
            TransferRequest request, String username, String idempotencyKey) {
        if (idempotencyKey != null
                && (idempotencyKey.isBlank() || idempotencyKey.length() > 100)) {
            throw new InvalidTransactionException("A valid Idempotency-Key is required.");
        }

        String normalizedOwnerEmail = username.toLowerCase(Locale.ROOT);
        BigDecimal amount = normalizedTransferAmount(request);
        LockedTransferAccounts locked = lockTransferAccounts(request, normalizedOwnerEmail, false);
        var existing = idempotencyKey == null ? Optional.<TransferIdempotencyRecord>empty()
                : transferIdempotencyRepository.findByOwnerEmailAndIdempotencyKey(
                        normalizedOwnerEmail, idempotencyKey);
        if (existing.isPresent()) {
            TransferIdempotencyRecord saved = existing.get();
            if (!saved.getSourceAccountId().equals(locked.source().getAccountId())
                    || !saved.getDestinationAccountId().equals(locked.destination().getAccountId())
                    || saved.getAmount().compareTo(amount) != 0) {
                throw new DuplicateResourceException(
                        "This Idempotency-Key has already been used for a different transfer.");
            }
            if (TransactionStatus.FAILED.name().equals(saved.getOutcomeStatus())) {
                throw new InsufficientBalanceException(saved.getFailureMessage());
            }
            return replayResponse(saved, normalizedOwnerEmail);
        }

        TransferRecipientResponse recipient = maskedRecipient(locked.destination());
        PostedTransfer posted;
        try {
            posted = applyTransfer(locked.source(), locked.destination(), amount);
        } catch (InsufficientBalanceException exception) {
            rememberTransferOutcome(normalizedOwnerEmail, idempotencyKey, amount, locked,
                    recipient, null, TransactionStatus.FAILED, exception.getMessage());
            throw exception;
        }

        rememberTransferOutcome(normalizedOwnerEmail, idempotencyKey, amount, locked,
                recipient, posted.referenceNumber(), TransactionStatus.POSTED, null);
        return new CustomerTransferResponse(
                BankingMapper.toAccountResponse(posted.source()), recipient, posted.referenceNumber());
    }

    private void rememberTransferOutcome(String ownerEmail, String idempotencyKey, BigDecimal amount,
                                         LockedTransferAccounts accounts, TransferRecipientResponse recipient,
                                         String reference, TransactionStatus status, String failureMessage) {
        if (idempotencyKey == null) {
            return;
        }
        BankAccount source = accounts.source();
        transferIdempotencyRepository.saveAndFlush(new TransferIdempotencyRecord(
                ownerEmail,
                idempotencyKey,
                source.getAccountId(),
                accounts.destination().getAccountId(),
                amount,
                reference,
                source.getAccountNumber(),
                source.getHolderName(),
                source.getBalance(),
                recipient.maskedName(),
                status.name(),
                failureMessage
        ));
    }

    private CustomerTransferResponse replayResponse(TransferIdempotencyRecord saved, String username) {
        AccountResponse originalSource = new AccountResponse(
                saved.getSourceAccountId(),
                saved.getSourceAccountNumber(),
                saved.getSourceHolderName(),
                saved.getSourceBalance(),
                true,
                username
        );
        return new CustomerTransferResponse(
                originalSource,
                new TransferRecipientResponse(saved.getMaskedRecipientName()),
                saved.getReferenceNumber()
        );
    }

    private PostedTransfer postTransfer(TransferRequest request, String username, boolean admin) {
        LockedTransferAccounts accounts = lockTransferAccounts(request, username, admin);
        return applyTransfer(accounts.source(), accounts.destination(), normalizedTransferAmount(request));
    }

    private BigDecimal normalizedTransferAmount(TransferRequest request) {
        if (request.fromAccountId() == null) {
            throw new InvalidTransactionException("Source account ID is required");
        }
        validatePositiveAmount(request.amount());
        try {
            return request.amount().setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException exception) {
            throw new InvalidTransactionException("Amount cannot have more than two decimal places");
        }
    }

    private LockedTransferAccounts lockTransferAccounts(
            TransferRequest request, String username, boolean admin) {
        Long sourceAccountId = request.fromAccountId();
        if (sourceAccountId == null) {
            throw new InvalidTransactionException("Source account ID is required");
        }
        if (!admin && !bankAccountRepository.existsByAccountIdAndOwnerEmailIgnoreCase(sourceAccountId, username)) {
            throw new AccessDeniedBusinessException("You can only access your own accounts");
        }

        Long destinationAccountId;
        if (request.toAccountNumber() != null && !request.toAccountNumber().isBlank()) {
            destinationAccountId = bankAccountRepository
                    .findAccountIdByAccountNumber(request.toAccountNumber().trim())
                    .orElseThrow(() -> new AccountNotFoundException("Destination account not found"));
        } else if (request.toAccountId() != null) {
            destinationAccountId = request.toAccountId();
        } else {
            throw new InvalidTransactionException("Destination account ID or account number is required");
        }
        if (sourceAccountId.equals(destinationAccountId)) {
            throw new InvalidTransactionException("Cannot transfer money to the same account");
        }

        boolean sourceFirst = sourceAccountId < destinationAccountId;
        BankAccount first = lockAccount(sourceFirst ? sourceAccountId : destinationAccountId);
        BankAccount second = lockAccount(sourceFirst ? destinationAccountId : sourceAccountId);
        BankAccount source = sourceFirst ? first : second;
        BankAccount destination = sourceFirst ? second : first;
        ensureOwnerOrAdmin(source, username, admin);
        return new LockedTransferAccounts(source, destination);
    }

    private BankAccount lockAccount(Long accountId) {
        return bankAccountRepository.findByIdForUpdate(accountId)
                .orElseThrow(() -> new AccountNotFoundException("Account not found"));
    }

    private PostedTransfer applyTransfer(BankAccount source, BankAccount destination, BigDecimal amount) {
        ensureActive(source);
        ensureActive(destination);
        if (source.getBalance().compareTo(amount) < 0) {
            transactionAttemptService.recordTransferFailure(
                    source,
                    amount,
                    "Insufficient balance for transfer"
            );
            throw new InsufficientBalanceException("Insufficient balance for transfer");
        }

        String reference = generateReferenceNumber();
        source.setBalance(source.getBalance().subtract(amount));
        destination.setBalance(destination.getBalance().add(amount));
        source.addTransaction(new Transaction(
                TransactionType.TRANSFER_SENT,
                amount,
                reference + "S",
                "Transfer " + reference + " to account " + destination.getAccountNumber()
        ));
        destination.addTransaction(new Transaction(
                TransactionType.TRANSFER_RECEIVED,
                amount,
                reference + "R",
                "Transfer " + reference + " from account " + source.getAccountNumber()
        ));
        bankAccountRepository.save(source);
        bankAccountRepository.save(destination);
        return new PostedTransfer(source, destination, reference);
    }

    private TransferRecipientResponse maskedRecipient(BankAccount recipient) {
        String[] names = recipient.getHolderName().strip().split("\\s+", 2);
        String givenName = names[0];
        String surname = names.length == 2 ? names[1] : names[0];
        String initial = surname.substring(0, surname.offsetByCodePoints(0, 1));
        return new TransferRecipientResponse(
                names.length == 2 ? givenName + " " + initial + "•••" : initial + "•••"
        );
    }

    private record LockedTransferAccounts(BankAccount source, BankAccount destination) {
    }

    private record PostedTransfer(BankAccount source, BankAccount destination, String referenceNumber) {
    }

    @Override
    @Transactional(readOnly = true)
    public Page<TransactionResponse> getTransactions(Long accountId, Pageable pageable, String username, boolean admin) {
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        return transactionRepository.findByBankAccountAccountIdOrderByTimestampDesc(accountId, pageable)
                .map(BankingMapper::toTransactionResponse);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<AdminTransactionResponse> getAllTransactions(Pageable pageable) {
        return transactionRepository.findAllByOrderByTimestampDesc(pageable)
                .map(this::toAdminTransactionResponse);
    }

    @Override
    @Transactional(readOnly = true)
    public String exportStatementCsv(Long accountId, String username, boolean admin) {
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);
        StringBuilder csv = new StringBuilder("Account Number,Holder Name,Transaction ID,Reference,Type,Status,Amount,Timestamp,Description,Failure Reason\n");
        transactionRepository.findByBankAccountAccountIdOrderByTimestampDesc(accountId)
                .forEach(transaction -> csv.append(account.getAccountNumber()).append(',')
                        .append(escapeCsv(account.getHolderName())).append(',')
                        .append(transaction.getId()).append(',')
                        .append(transaction.getReferenceNumber()).append(',')
                        .append(transaction.getType()).append(',')
                        .append(transaction.getStatus()).append(',')
                        .append(transaction.getAmount()).append(',')
                        .append(transaction.getTimestamp()).append(',')
                        .append(escapeCsv(transaction.getDescription())).append(',')
                        .append(escapeCsv(transaction.getFailureReason()))
                        .append('\n'));
        return csv.toString();
    }

    @Override
    @Transactional(readOnly = true)
    public String exportAccountsCsv() {
        StringBuilder csv = new StringBuilder("Account ID,Account Number,Holder Name,Owner Email,Balance,Active\n");
        bankAccountRepository.findAll()
                .forEach(account -> csv.append(account.getAccountId()).append(',')
                        .append(account.getAccountNumber()).append(',')
                        .append(escapeCsv(account.getHolderName())).append(',')
                        .append(escapeCsv(account.getOwner().getEmail())).append(',')
                        .append(account.getBalance()).append(',')
                        .append(account.isActive())
                        .append('\n'));
        return csv.toString();
    }

    @Override
    @Transactional(readOnly = true)
    public String exportTransactionsCsv() {
        StringBuilder csv = new StringBuilder("Transaction ID,Account ID,Account Number,Owner Email,Reference,Type,Status,Amount,Timestamp,Description,Failure Reason\n");
        transactionRepository.findAllByOrderByTimestampDesc()
                .forEach(transaction -> csv.append(transaction.getId()).append(',')
                        .append(transaction.getBankAccount().getAccountId()).append(',')
                        .append(transaction.getBankAccount().getAccountNumber()).append(',')
                        .append(escapeCsv(transaction.getBankAccount().getOwner().getEmail())).append(',')
                        .append(transaction.getReferenceNumber()).append(',')
                        .append(transaction.getType()).append(',')
                        .append(transaction.getStatus()).append(',')
                        .append(transaction.getAmount()).append(',')
                        .append(transaction.getTimestamp()).append(',')
                        .append(escapeCsv(transaction.getDescription())).append(',')
                        .append(escapeCsv(transaction.getFailureReason()))
                        .append('\n'));
        return csv.toString();
    }

    @Override
    @Transactional(readOnly = true)
    public AdminSummaryResponse getAdminSummary() {
        var accounts = bankAccountRepository.findAll();
        BigDecimal totalBalance = accounts.stream()
                .map(BankAccount::getBalance)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        long activeAccounts = accounts.stream().filter(BankAccount::isActive).count();

        return new AdminSummaryResponse(
                accounts.size(),
                activeAccounts,
                accounts.size() - activeAccounts,
                transactionRepository.count(),
                totalBalance
        );
    }

    @Override
    @Transactional(readOnly = true)
    public RiskInsightResponse getRiskInsights(Long accountId, String username, boolean admin) {
        BankAccount account = findAccount(accountId);
        ensureOwnerOrAdmin(account, username, admin);

        List<Transaction> transactions = transactionRepository.findByBankAccountAccountIdOrderByTimestampDesc(accountId);
        BigDecimal totalCredits = BigDecimal.ZERO;
        BigDecimal totalDebits = BigDecimal.ZERO;
        BigDecimal largestTransaction = BigDecimal.ZERO;
        long transferSentCount = 0;
        long recentTransactionCount = 0;
        long failedTransactionCount = 0;
        LocalDateTime oneDayAgo = LocalDateTime.now().minusDays(1);

        for (Transaction transaction : transactions) {
            if (transaction.getStatus() == TransactionStatus.FAILED) {
                failedTransactionCount++;
                continue;
            }
            BigDecimal amount = transaction.getAmount();
            if (amount.compareTo(largestTransaction) > 0) {
                largestTransaction = amount;
            }
            if (isCredit(transaction)) {
                totalCredits = totalCredits.add(amount);
            } else {
                totalDebits = totalDebits.add(amount);
            }
            if (transaction.getType() == TransactionType.TRANSFER_SENT) {
                transferSentCount++;
            }
            if (transaction.getTimestamp() != null && transaction.getTimestamp().isAfter(oneDayAgo)) {
                recentTransactionCount++;
            }
        }

        List<RiskSignalResponse> signals = new ArrayList<>();
        int score = 0;

        if (totalDebits.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal debitToCreditRatio = totalCredits.compareTo(BigDecimal.ZERO) == 0
                    ? BigDecimal.valueOf(999)
                    : totalDebits.divide(totalCredits, 2, RoundingMode.HALF_UP);
            if (debitToCreditRatio.compareTo(new BigDecimal("0.80")) >= 0) {
                score += addSignal(signals, "BALANCE_DRAIN", "High debit pressure",
                        "Debits are close to or above credits, which can indicate liquidity stress.", 28);
            }
        }

        if (transactions.size() >= 4 && largestTransaction.compareTo(account.getBalance().max(BigDecimal.ONE).multiply(new BigDecimal("0.60"))) >= 0) {
            score += addSignal(signals, "LARGE_TRANSACTION", "Large transaction concentration",
                    "The largest transaction is significant relative to the current balance.", 22);
        }

        if (transferSentCount >= 3) {
            score += addSignal(signals, "TRANSFER_VELOCITY", "Repeated outbound transfers",
                    "Multiple outbound transfers may require review for unusual movement patterns.", 20);
        }

        if (recentTransactionCount >= 5) {
            score += addSignal(signals, "RECENT_ACTIVITY", "High recent activity",
                    "Five or more transactions occurred in the last 24 hours.", 18);
        }

        if (failedTransactionCount >= 2) {
            score += addSignal(signals, "FAILED_ATTEMPTS", "Repeated failed attempts",
                    "Two or more failed money-movement attempts require review.", 25);
        }

        if (!account.isActive()) {
            score += addSignal(signals, "CLOSED_ACCOUNT", "Closed account",
                    "The account is closed and should not be used for new money movement.", 12);
        }

        score = Math.min(score, 100);
        String riskLevel = score >= 70 ? "HIGH" : score >= 35 ? "MEDIUM" : "LOW";
        String recommendation = switch (riskLevel) {
            case "HIGH" -> "Escalate for manual review before further high-value transfers.";
            case "MEDIUM" -> "Monitor upcoming activity and verify large outbound payments.";
            default -> "No immediate action required. Continue standard monitoring.";
        };

        return new RiskInsightResponse(
                account.getAccountId(),
                account.getAccountNumber(),
                riskLevel,
                score,
                account.getBalance(),
                totalCredits,
                totalDebits,
                largestTransaction,
                transactions.size(),
                signals,
                recommendation
        );
    }

    private BankAccount findAccount(Long accountId) {
        return bankAccountRepository.findById(accountId)
                .orElseThrow(() -> new AccountNotFoundException("Account not found"));
    }

    private boolean accountMatches(BankAccount account, String query) {
        return String.valueOf(account.getAccountId()).contains(query)
                || account.getAccountNumber().toLowerCase(Locale.ROOT).contains(query)
                || account.getHolderName().toLowerCase(Locale.ROOT).contains(query)
                || account.getOwner().getEmail().toLowerCase(Locale.ROOT).contains(query);
    }

    private AdminTransactionResponse toAdminTransactionResponse(Transaction transaction) {
        BankAccount account = transaction.getBankAccount();
        return new AdminTransactionResponse(
                transaction.getId(),
                account.getAccountId(),
                account.getAccountNumber(),
                account.getOwner().getEmail(),
                transaction.getType(),
                transaction.getAmount(),
                transaction.getTimestamp(),
                transaction.getReferenceNumber(),
                transaction.getDescription(),
                transaction.getStatus(),
                transaction.getFailureReason()
        );
    }

    private void ensureActive(BankAccount account) {
        if (!account.isActive()) {
            throw new AccountClosedException("Account is closed");
        }
    }

    private void ensureOwnerOrAdmin(BankAccount account, String username, boolean admin) {
        if (admin) {
            return;
        }
        if (!account.getOwner().getEmail().equalsIgnoreCase(username)) {
            throw new AccessDeniedBusinessException("You can only access your own accounts");
        }
    }

    private void validatePositiveAmount(BigDecimal amount) {
        if (amount == null || amount.compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidTransactionException("Amount must be greater than zero");
        }
    }

    private String generateAccountNumber() {
        String accountNumber;
        do {
            accountNumber = String.valueOf(ThreadLocalRandom.current().nextLong(100_000_000_000L, 999_999_999_999L));
        } while (bankAccountRepository.findByAccountNumber(accountNumber).isPresent());
        return accountNumber;
    }

    private String generateReferenceNumber() {
        return "TXN" + UUID.randomUUID().toString().replace("-", "").substring(0, 16).toUpperCase();
    }

    private boolean isCredit(Transaction transaction) {
        return transaction.getType() == TransactionType.OPENING_DEPOSIT
                || transaction.getType() == TransactionType.DEPOSIT
                || transaction.getType() == TransactionType.TRANSFER_RECEIVED;
    }

    private int addSignal(List<RiskSignalResponse> signals, String code, String title, String detail, int points) {
        signals.add(new RiskSignalResponse(code, title, detail, points));
        return points;
    }

    private String escapeCsv(String value) {
        if (value == null) {
            return "";
        }
        String escaped = value.replace("\"", "\"\"");
        if (escaped.contains(",") || escaped.contains("\"") || escaped.contains("\n")) {
            return "\"" + escaped + "\"";
        }
        return escaped;
    }
}
