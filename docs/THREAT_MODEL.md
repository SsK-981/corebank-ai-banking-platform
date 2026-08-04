# Threat model and boundaries

## Protected assets

- Customer identity and KYC state
- Account ownership, balances, and transaction history
- Service credentials and LLM API keys
- Conversation and support-ticket content
- Administrative operations

## Implemented controls

- Customer-scoped JWT authorization and role checks
- CoreBank ownership validation on every account read
- Separate AI service credential; no customer banking password storage in the agent
- Redaction before optional LLM calls
- Deterministic financial response rendering
- Optimistic locking and atomic transfer transactions
- Failed-attempt persistence and explainable manual-review signals
- Security headers, request IDs, audit events, and no-store responses
- Production configuration guards and migration-controlled schemas

## Required before real deployment

- Managed OIDC/OAuth identity provider and short-lived service identities or mTLS
- TLS at every network hop and managed secret storage
- Central rate limiting, abuse detection, metrics, traces, and alerting
- Encryption and retention/deletion policies for conversation data
- Backup restoration tests and disaster-recovery objectives
- Independent penetration testing, dependency scanning, and compliance review
- Validated fraud/risk models and documented human decision procedures

This project intentionally makes these boundaries visible rather than claiming that a
portfolio application is a regulated banking platform.
