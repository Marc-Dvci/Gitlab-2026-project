# Carbon receipt v1

A carbon receipt is an [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
attached to every container image, signed keylessly with Sigstore from the GitLab CI job's OIDC
identity and recorded in the Rekor transparency log.

- `predicateType`: `urn:joulethief:carbon-receipt:v1` (override with `JOULE_PREDICATE_TYPE`, e.g. the
  GitLab Pages URL of this document once published)
- `subject`: the image name and its `sha256` manifest digest

## Predicate

```json
{
  "version": "1",
  "generatedAt": "2026-10-06T12:00:00+00:00",
  "methodology": { "sci": "ISO/IEC 21031:2024 ...", "sci_for_ai": "...", "ledgers": ["..."], "...": "..." },
  "pipeline": { "CI_PROJECT_PATH": "...", "CI_PIPELINE_ID": "...", "CI_COMMIT_SHA": "...", "CI_JOB_URL": "..." },
  "build": {
    "energy_kwh":       { "low": 0.0, "likely": 0.0, "high": 0.0 },
    "attributional_g":  { "low": 0.0, "likely": 0.0, "high": 0.0 },
    "consequential_g":  { "low": 0.0, "likely": 0.0, "high": 0.0 },
    "water_l":          { "low": 0.0, "likely": 0.0, "high": 0.0 },
    "surplus_energy_share": 0.0
  },
  "agents":  { "energy_kwh": {}, "gwp_g": {}, "water_l": {}, "input_tokens": 0, "output_tokens": 0, "sci_for_ai": {} },
  "runtime": { "sci_g_per_1000_requests": {} },
  "signals": [ { "source": "...", "zone": "FI", "metric": "day_ahead_price", "fetched_at": "...", "sha256": "..." } ],
  "budget":  { "period": "2026-10", "capG": 5000, "spentG": 120.5, "remainingG": 4879.5 },
  "verdict": "within-budget"
}
```

## Verify a receipt yourself

```bash
cosign verify-attestation --type urn:joulethief:carbon-receipt:v1 \
  --certificate-identity "https://gitlab.com/<group>/<project>//.gitlab-ci.yml@refs/heads/main" \
  --certificate-oidc-issuer https://gitlab.com \
  registry.gitlab.com/<group>/<project>/app@sha256:<digest> | head -n1 > envelope.json
python -m joulethief.cli receipt verify --statement envelope.json --digest <digest>
```

The content policy (`joulethief/receipts/intoto.py`) rejects receipts that are over budget, lack
ranges, use signals older than 36 h, or whose subject digest does not match the deployed image.
