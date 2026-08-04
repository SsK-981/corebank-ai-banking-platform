package com.example.bankingapp.repository;

import com.example.bankingapp.model.Transaction;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface TransactionRepository extends JpaRepository<Transaction, Long> {
    Page<Transaction> findByBankAccountAccountIdOrderByTimestampDesc(Long accountId, Pageable pageable);

    List<Transaction> findByBankAccountAccountIdOrderByTimestampDesc(Long accountId);

    Page<Transaction> findAllByOrderByTimestampDesc(Pageable pageable);

    List<Transaction> findAllByOrderByTimestampDesc();
}
