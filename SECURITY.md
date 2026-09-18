# Security policy

## Supported versions

Security fixes are applied to the latest version on the default branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature instead of opening a public issue. Include affected versions, reproduction steps and the expected impact. If private reporting is unavailable, contact the repository owner through the address listed on their GitHub profile.

Do not include real user photos, API keys or other sensitive data in a report. Replace them with synthetic samples and redacted values.

## Deployment notes

Set `VTON_API_KEY` before exposing the API outside localhost, place the service behind HTTPS, restrict upload size at the reverse proxy, and keep the data retention period short. Public-demo mode sends images to a third-party Hugging Face Space after explicit consent; use local or controlled remote inference for private images.
