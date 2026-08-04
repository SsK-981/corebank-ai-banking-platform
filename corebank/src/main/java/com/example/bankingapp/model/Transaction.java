package com.example.bankingapp.model;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import com.fasterxml.jackson.annotation.JsonIgnore;


@Entity
@Table(name = "account_transaction")
public class Transaction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private TransactionType type;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(nullable = false)
    private LocalDateTime timestamp;

    @Column(nullable = false, unique = true, length = 24)
    private String referenceNumber;

    private String description;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private TransactionStatus status = TransactionStatus.POSTED;

    @Column(length = 500)
    private String failureReason;

    @ManyToOne
    @JoinColumn(name = "account_id")
    @JsonIgnore
    private BankAccount bankAccount;

    public Transaction() {
    }

    public Transaction(TransactionType type, BigDecimal amount, String referenceNumber, String description) {
        this(type, amount, referenceNumber, description, TransactionStatus.POSTED, null);
    }

    public Transaction(TransactionType type, BigDecimal amount, String referenceNumber,
                       String description, TransactionStatus status, String failureReason) {
        this.type = type;
        this.amount = amount;
        this.referenceNumber = referenceNumber;
        this.description = description;
        this.status = status;
        this.failureReason = failureReason;
        this.timestamp = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public TransactionType getType() {
        return type;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public LocalDateTime getTimestamp() {
        return timestamp;
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public String getDescription() {
        return description;
    }

    public TransactionStatus getStatus() {
        return status;
    }

    public String getFailureReason() {
        return failureReason;
    }

    public BankAccount getBankAccount() {
        return bankAccount;
    }

    public void setBankAccount(BankAccount bankAccount) {
        this.bankAccount = bankAccount;
    }
}
