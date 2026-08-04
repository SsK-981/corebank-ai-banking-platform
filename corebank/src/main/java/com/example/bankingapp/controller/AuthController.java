package com.example.bankingapp.controller;

import com.example.bankingapp.dto.RegisterRequest;
import com.example.bankingapp.dto.UserResponse;
import com.example.bankingapp.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    public UserResponse register(@Valid @RequestBody RegisterRequest request) {
        return authService.registerCustomer(request);
    }

    @PostMapping("/customer/register")
    public UserResponse registerCustomer(@Valid @RequestBody RegisterRequest request) {
        return authService.registerCustomer(request);
    }

    @PostMapping("/admin/register")
    public UserResponse registerAdmin(@Valid @RequestBody RegisterRequest request) {
        return authService.registerAdmin(request);
    }

    @GetMapping("/me")
    public UserResponse me(Authentication authentication) {
        return authService.getCurrentUser(authentication.getName());
    }

    @GetMapping("/customer/me")
    public UserResponse customerMe(Authentication authentication) {
        return authService.getCurrentUser(authentication.getName());
    }

    @GetMapping("/admin/me")
    public UserResponse adminMe(Authentication authentication) {
        return authService.getCurrentUser(authentication.getName());
    }
}
