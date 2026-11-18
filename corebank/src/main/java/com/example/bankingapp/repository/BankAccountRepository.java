package com.example.bankingapp.repository;

import com.example.bankingapp.model.BankAccount;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface BankAccountRepository extends JpaRepository<BankAccount, Long> {
    Optional<BankAccount> findByAccountNumber(String accountNumber);

    @Query("select account.accountId from BankAccount account where account.accountNumber = :accountNumber")
    Optional<Long> findAccountIdByAccountNumber(@Param("accountNumber") String accountNumber);

    boolean existsByAccountIdAndOwnerEmailIgnoreCase(Long accountId, String ownerEmail);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select account from BankAccount account where account.accountId = :accountId")
    Optional<BankAccount> findByIdForUpdate(@Param("accountId") Long accountId);

    Page<BankAccount> findByOwnerEmailIgnoreCase(String email, Pageable pageable);

    boolean existsByOwnerEmailIgnoreCase(String email);
}
