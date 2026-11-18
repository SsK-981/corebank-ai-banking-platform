package com.example.bankingapp.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "transfer_idempotency", uniqueConstraints = @UniqueConstraint(
        name = "uk_transfer_idempotency_owner_key", columnNames = {"owner_email", "idempotency_key"}))
public class TransferIdempotencyRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_email", nullable = false, length = 255)
    private String ownerEmail;

    @Column(name = "idempotency_key", nullable = false, length = 100)
    private String idempotencyKey;

    @Column(name = "source_account_id", nullable = false)
    private Long sourceAccountId;

    @Column(name = "destination_account_id", nullable = false)
    private Long destinationAccountId;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "reference_number", length = 19)
    private String referenceNumber;

    @Column(name = "outcome_status", nullable = false, length = 20)
    private String outcomeStatus;

    @Column(name = "failure_message", length = 255)
    private String failureMessage;

    @Column(name = "source_account_number", nullable = false, length = 12)
    private String sourceAccountNumber;

    @Column(name = "source_holder_name", nullable = false, length = 255)
    private String sourceHolderName;

    @Column(name = "source_balance", nullable = false, precision = 19, scale = 2)
    private BigDecimal sourceBalance;

    @Column(name = "masked_recipient_name", nullable = false, length = 255)
    private String maskedRecipientName;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    protected TransferIdempotencyRecord() {
    }

    public TransferIdempotencyRecord(String ownerEmail, String idempotencyKey, Long sourceAccountId,
                                     Long destinationAccountId, BigDecimal amount, String referenceNumber,
                                     String sourceAccountNumber, String sourceHolderName, BigDecimal sourceBalance,
                                     String maskedRecipientName, String outcomeStatus, String failureMessage) {
        this.ownerEmail = ownerEmail;
        this.idempotencyKey = idempotencyKey;
        this.sourceAccountId = sourceAccountId;
        this.destinationAccountId = destinationAccountId;
        this.amount = amount;
        this.referenceNumber = referenceNumber;
        this.sourceAccountNumber = sourceAccountNumber;
        this.sourceHolderName = sourceHolderName;
        this.sourceBalance = sourceBalance;
        this.maskedRecipientName = maskedRecipientName;
        this.outcomeStatus = outcomeStatus;
        this.failureMessage = failureMessage;
    }

    public Long getSourceAccountId() { return sourceAccountId; }
    public Long getDestinationAccountId() { return destinationAccountId; }
    public BigDecimal getAmount() { return amount; }
    public String getReferenceNumber() { return referenceNumber; }
    public String getOutcomeStatus() { return outcomeStatus; }
    public String getFailureMessage() { return failureMessage; }
    public String getSourceAccountNumber() { return sourceAccountNumber; }
    public String getSourceHolderName() { return sourceHolderName; }
    public BigDecimal getSourceBalance() { return sourceBalance; }
    public String getMaskedRecipientName() { return maskedRecipientName; }
}
