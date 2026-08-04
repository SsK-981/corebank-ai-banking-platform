# GitHub upload checklist

Use this when publishing the project as a portfolio repository.

## Repository settings

Recommended repository name:

```text
fintech-ai-agent-chatbot
```

Short description:

```text
Grounded AI banking support platform with Spring Boot, FastAPI, Streamlit, PostgreSQL, Docker, and cross-service tests.
```

Suggested topics:

```text
fintech, ai-agent, banking, spring-boot, fastapi, streamlit, postgresql, docker, risk-engine, jwt-auth
```

Visibility:

```text
Public, if you want it visible on your GitHub profile.
```

## Before pushing

- Keep `.env` private. It is already ignored by `.gitignore`.
- Keep screenshots under `docs/screenshots/`; the README references them directly.
- Replace local demo credentials before any real deployment.
- Use the README screenshots and `docs/DEMO.md` as your interview walkthrough.

## First push

If Git is not configured on this machine:

```powershell
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```

Create an empty repository on GitHub, then run:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/fintech-ai-agent-chatbot.git
git branch -M main
git add .
git commit -m "Initial portfolio-ready fintech AI support platform"
git push -u origin main
```

If `origin` already exists, update it instead:

```powershell
git remote set-url origin https://github.com/YOUR_USERNAME/fintech-ai-agent-chatbot.git
```

## Profile polish

After pushing:

1. Open the repository on GitHub and confirm the README renders screenshots.
2. Add the short description and topics above in the repository About panel.
3. Pin the repository on your GitHub profile.
4. In the profile pinned-card description, use:

```text
Grounded AI banking support platform: Spring Boot CoreBank, FastAPI agent, Streamlit UI, PostgreSQL, Docker, and CI.
```

5. Use the resume line from the README when describing the project in applications.
