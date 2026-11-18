package com.example.bankingapp.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;
import java.util.Map;

@RestController
@RequestMapping("/customer/support")
public class CustomerSupportController {
    private final RestClient restClient;
    private final String supportServiceToken;

    public CustomerSupportController(
            @Value("${app.support.api-url:http://127.0.0.1:8000}") String apiUrl,
            @Value("${app.support.service-token:local-support-service-token-change-me}") String supportServiceToken) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(3));
        requestFactory.setReadTimeout(Duration.ofSeconds(30));
        this.restClient = RestClient.builder()
                .baseUrl(apiUrl)
                .requestFactory(requestFactory)
                .build();
        this.supportServiceToken = supportServiceToken;
    }

    @PostMapping(value = "/chat", consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> chat(@RequestBody ChatPayload payload, Authentication authentication) {
        if (payload.message() == null || payload.message().isBlank() || payload.message().length() > 2000
                || (payload.conversation_id() != null && payload.conversation_id().length() != 36)) {
            return ResponseEntity.badRequest().body(Map.of("detail", "Invalid support chat request."));
        }
        try {
            String response = restClient.post().uri("/internal/support/chat")
                    .header("X-Support-Service-Token", supportServiceToken)
                    .header("X-Authenticated-Customer-Email", authentication.getName())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(payload)
                    .retrieve()
                    .body(String.class);
            return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(response);
        } catch (RestClientException exception) {
            HttpStatus status = HttpStatus.BAD_GATEWAY;
            String message = "Support is temporarily unavailable. Please try again.";
            if (exception instanceof HttpStatusCodeException upstream) {
                if (upstream.getStatusCode().value() == 403) {
                    status = HttpStatus.FORBIDDEN;
                    message = upstream.getResponseBodyAsString().contains("Conversation access denied")
                            ? "This conversation is unavailable for your account."
                            : "Support chat is available only for the configured CoreBank demo customers.";
                } else if (upstream.getStatusCode().value() == 503) {
                    status = HttpStatus.SERVICE_UNAVAILABLE;
                } else if (upstream.getStatusCode().is4xxClientError()
                        && upstream.getStatusCode().value() != 401) {
                    status = HttpStatus.BAD_REQUEST;
                    message = "The support chat request could not be processed.";
                }
            }
            return ResponseEntity.status(status).body(Map.of("detail", message));
        }
    }

    public record ChatPayload(
            String message,
            String conversation_id,
            String action,
            String transaction_reference
    ) {}

}
