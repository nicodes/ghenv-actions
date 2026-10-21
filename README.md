# ghenv-actions

Reusable GitHub Action for the encrypted Preview credential handoff used by
[`ghenv`](https://github.com/nicodes/ghenv). Your application runs locally; this
action runs in the project's GitHub Actions job and uploads only ciphertext.

```yaml
- uses: nicodes/ghenv-actions@<full-commit-sha>
  with:
    preview-bundle: ${{ secrets.GHENV_PREVIEW_BUNDLE }}
    request-id: ${{ inputs.request_id }}
    public-key: ${{ inputs.public_key }}
    secret-names: ${{ inputs.secret_names }}
    variable-names: ${{ inputs.variable_names }}
```

## Project setup

1. Create the project's `Preview` environment and configure its protection rules.
2. Add the owner-curated `GHENV_PREVIEW_BUNDLE` secret described below.
3. Copy [examples/ghenv.yml](examples/ghenv.yml) to `.github/workflows/ghenv.yml`
   in that project. Replace `FULL_ACTION_COMMIT_SHA` with a reviewed action
   commit. Keep the job fixed to `environment: Preview`.
4. Install the workflow on the project's default branch for normal use, then run:

```sh
ghenv run --repo OWNER/PROJECT --secrets API_KEY --vars API_BASE_URL -- npm run dev
```

No checkout of application code is needed in the handoff job. The action builds
the exporter from the fixed Go source commit in [ghenv-source](ghenv-source)
using an isolated Git fetch, commit verification, and build. It does not build the calling project's
code or accept a caller-selected exporter version. Updating the action's full
commit pin is an explicit trust decision; review changes to its Go source pin too.

The action requires a Linux runner with Bash and network access to GitHub/Go
module services. It installs Go with a pinned GitHub-owned setup action. The
provided workflow uses a fresh GitHub-hosted runner and `contents: read`.
The local CLI needs Actions read/write for dispatch and artifact deletion.

## Preview bundle

Store a JSON object like this in the project's `Preview` environment as
`GHENV_PREVIEW_BUNDLE` (maximum 48 KiB):

```json
{
  "version": 1,
  "environment": "Preview",
  "repository": "OWNER/PROJECT",
  "secrets": { "API_KEY": "development-only-value" },
  "variables": { "API_BASE_URL": "http://127.0.0.1:3000" }
}
```

Both maps are required; use `{}` for an empty map. Entry values must be strings.
Field names and repository casing must match exactly. Nulls, ambiguous or
unknown schema fields, invalid names, NUL bytes, Production/foreign bundles,
and names outside these maps are rejected by the Go exporter. The repository
is checked against the runner's `GITHUB_REPOSITORY`, not a dispatch input.

This bundle is the complete owner-approved export allowlist. Dispatchers who
obtain required environment approval may select any entry in it, including
through direct GitHub API calls. Standalone Actions entries are not imported.
Pass only this fixed secret; never pass `toJSON(secrets)` or inherit an entire
secret context.

Reserve this bundle name exclusively for development credentials at every
GitHub scope. GitHub does not attest an individual merged-context secret's
origin. A valid Preview-marked bundle at repository/organization scope can be
selected through GitHub fallback. The exporter rejects correctly labelled
Production bundles; it cannot classify a production key an owner incorrectly
labels as Preview. Restrict bundle, workflow, and action maintainers accordingly.

## Inputs and outputs

| Input | Purpose |
| --- | --- |
| `environment` | Defaults to `Preview`; other values are rejected. The caller must also fix its job's environment to Preview. |
| `preview-bundle` | The fixed `GHENV_PREVIEW_BUNDLE` secret. Required. |
| `public-key` | CLI-generated ephemeral RSA public key, base64 DER. Required. |
| `request-id` | CLI-generated 32-character lowercase hexadecimal identifier. Required. |
| `secret-names` | Comma-separated entries from the bundle's `secrets` map. |
| `variable-names` | Comma-separated entries from the bundle's `variables` map. |

The caller must request at least one name. Input values are passed through
environment variables, not interpolated into shell code. The bundle is supplied
only to the encryption step; do not also put it in job-wide environment variables.

Outputs `artifact-id` and `artifact-url` identify the ciphertext artifact named
`ghenv-<request-id>`. No plaintext values or payloads are returned as outputs.
The artifact has one-day retention. The CLI attempts to delete it after download;
interrupted clients may leave ciphertext until expiry.

Temporary exporter files and ciphertext are removed on action success or
failure. This cleanup cannot run if the runner is abruptly destroyed. The action
creates no plaintext credential files and does not receive the CLI's private key.

Local users, administrators, and the launched application can inspect injected
values. Credentials developers must never read must stay behind a remote API.
Browser-facing configuration remains public. Use reviewed workflow/action code
and fresh runners; the action is not a sandbox for other steps in its job.

## Verification

CI runs the real composite action with synthetic data, downloads its artifact,
and independently decrypts it to check exact values and exclusion of unrequested
entries. A second invocation rejects a Production-marked bundle and checks that
no artifact was uploaded and temporary state was removed. Script tests cover
invalid input and cleanup confinement. No real credentials are used.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
bash -n scripts/prepare.sh scripts/cleanup.sh
go vet ./tests/probe.go
```
