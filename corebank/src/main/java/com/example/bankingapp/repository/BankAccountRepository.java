package com.example.bankingapp.repository;

import com.example.bankingapp.model.BankAccount;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface BankAccountRepository extends JpaRepository<BankAccount, Long> {
    Optional<BankAccount> findByAccountNumber(String accountNumber);

    Page<BankAccount> findByOwnerEmailIgnoreCase(String email, Pageable pageable);

    boolean existsByOwnerEmailIgnoreCase(String email);
}
