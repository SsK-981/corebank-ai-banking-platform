package com.example.bankingapp.service;

import com.example.bankingapp.dto.RegisterRequest;
import com.example.bankingapp.dto.KycUpdateRequest;
import com.example.bankingapp.dto.UserResponse;
import com.example.bankingapp.model.AppUser;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface AuthService {
    UserResponse register(RegisterRequest request);

    UserResponse registerCustomer(RegisterRequest request);

    UserResponse registerAdmin(RegisterRequest request);

    UserResponse getCurrentUser(String email);

    AppUser findUser(String email);

    Page<UserResponse> getCustomers(Pageable pageable);

    UserResponse updateKyc(String email, KycUpdateRequest request);
}
