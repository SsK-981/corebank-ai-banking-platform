# Security policy

This repository is a portfolio/demo system and must use synthetic data only.

Do not report vulnerabilities through public issues when they contain exploit details,
credentials, or customer information. Contact the repository owner privately through
the email listed on their GitHub profile.

Never commit `.env`, API keys, JWT signing material, database files, or exported banking
statements. Local demo passwords in `.env.example` are intentionally non-production.

Production deployment requires the controls listed in `docs/THREAT_MODEL.md`.
