
# MarineVerse AWS Staging Checklist

## Account and budget

- [ ] AWS account plan verified
- [ ] Remaining credits checked
- [ ] Free Plan expiry recorded privately
- [ ] Root MFA enabled
- [ ] Zero-spend budget alert configured
- [ ] No paid-plan upgrade performed

## Deployment gates

- [ ] AWS region selected
- [ ] RDS PostgreSQL/PostGIS versions verified
- [ ] RDS cost and eligibility reviewed
- [ ] S3 storage cost and eligibility reviewed
- [ ] Network and backup costs reviewed
- [ ] Cloud database roles and privileges approved
- [ ] TLS and connection pooling verified
- [ ] Backup restoration approach verified

## Restrictions

- Do not commit AWS credentials or account identifiers.
- Do not provision resources before explicit approval.
- Do not upload local PostgreSQL data or raw datasets yet.
- Preserve all existing Objective 2 database and API contracts.
```

Do not commit this checklist yet.

### 5. Next checkpoint

Complete the AWS console checks and report only:

- Account plan
- Remaining credit amount
- Free Plan expiry date
- Whether MFA is enabled
- Whether the zero-spend alert was created

Do not share account numbers, billing details or credentials.

**PR-B status:** Compatibility checker committed and 165 tests passing. AWS staging safeguards are now the active milestone. Once verified, we'll choose the AWS region and evaluate RDS/S3 feasibility before provisioning anything.