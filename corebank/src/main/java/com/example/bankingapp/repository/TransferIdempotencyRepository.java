package com.example.bankingapp.repository;

import com.example.bankingapp.model.TransferIdempotencyRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface TransferIdempotencyRepository extends JpaRepository<TransferIdempotencyRecord, Long> {
    Optional<TransferIdempotencyRecord> findByOwnerEmailAndIdempotencyKey(
            String ownerEmail, String idempotencyKey);
}
