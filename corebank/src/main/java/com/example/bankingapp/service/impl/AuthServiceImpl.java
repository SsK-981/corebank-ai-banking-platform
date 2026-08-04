package com.example.bankingapp.service.impl;

import com.example.bankingapp.dto.RegisterRequest;
import com.example.bankingapp.dto.KycUpdateRequest;
import com.example.bankingapp.dto.UserResponse;
import com.example.bankingapp.exception.AccessDeniedBusinessException;
import com.example.bankingapp.exception.AccountNotFoundException;
import com.example.bankingapp.exception.DuplicateResourceException;
import com.example.bankingapp.model.AppUser;
import com.example.bankingapp.model.Role;
import com.example.bankingapp.repository.AppUserRepository;
import com.example.bankingapp.service.AuthService;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthServiceImpl implements AuthService {

    private final AppUserRepository appUserRepository;
    private final PasswordEncoder passwordEncoder;
    private final String adminCode;

    public AuthServiceImpl(AppUserRepository appUserRepository,
                           PasswordEncoder passwordEncoder,
                           @Value("${app.security.admin-code:admin123}") String adminCode) {
        this.appUserRepository = appUserRepository;
        this.passwordEncoder = passwordEncoder;
        this.adminCode = adminCode;
    }

    @Override
    @Transactional
    public UserResponse register(RegisterRequest request) {
        return registerCustomer(request);
    }

    @Override
    @Transactional
    public UserResponse registerCustomer(RegisterRequest request) {
        return createUser(request, Role.CUSTOMER);
    }

    @Override
    @Transactional
    public UserResponse registerAdmin(RegisterRequest request) {
        if (!adminCode.equals(request.adminCode())) {
            throw new AccessDeniedBusinessException("Invalid admin invite code");
        }
        return createUser(request, Role.ADMIN);
    }

    private UserResponse createUser(RegisterRequest request, Role role) {
        String email = request.email().trim().toLowerCase();
        if (appUserRepository.existsByEmailIgnoreCase(email)) {
            throw new DuplicateResourceException("Email is already registered");
        }

        AppUser user = new AppUser();
        user.setFullName(request.fullName().trim());
        user.setEmail(email);
        user.setPassword(passwordEncoder.encode(request.password()));
        user.setRole(role);

        return toResponse(appUserRepository.save(user));
    }

    @Override
    @Transactional(readOnly = true)
    public UserResponse getCurrentUser(String email) {
        return toResponse(findUser(email));
    }

    @Override
    @Transactional(readOnly = true)
    public AppUser findUser(String email) {
        return appUserRepository.findByEmailIgnoreCase(email)
                .orElseThrow(() -> new AccountNotFoundException("User not found"));
    }

    @Override
    @Transactional(readOnly = true)
    public Page<UserResponse> getCustomers(Pageable pageable) {
        return appUserRepository.findByRole(Role.CUSTOMER, pageable)
                .map(this::toResponse);
    }

    @Override
    @Transactional
    public UserResponse updateKyc(String email, KycUpdateRequest request) {
        AppUser user = findUser(email);
        if (user.getRole() != Role.CUSTOMER) {
            throw new AccessDeniedBusinessException("KYC can only be updated for customers");
        }
        user.setKycStatus(request.status());
        return toResponse(appUserRepository.save(user));
    }

    private UserResponse toResponse(AppUser user) {
        return new UserResponse(
                user.getId(),
                user.getFullName(),
                user.getEmail(),
                user.getRole(),
                user.getKycStatus()
        );
    }
}
