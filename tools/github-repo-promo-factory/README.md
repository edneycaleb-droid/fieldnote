# GitHub Repo Promo Factory

A free, local-first replacement for product-link promo generators. Give it a GitHub repository and it creates accurate, cinematic motion graphics without fabricating code or UI text.

## Outputs

- 1920×1080 H.264 promo
- 1080×1920 vertical promo
- 960×540 README GIF
- Reproducible JSON manifest
- Optional WanGP cinematic background prompts
- Manual GitHub Actions renderer

## Quick start

Requires Node.js 22+. Clone this repository, then:

```bash
npm install
npm run promo -- --repo edneycaleb-droid/fieldnote
```

Results are written to `out/OWNER-REPO/`. Preview and edit scenes with:

```bash
npm run studio
```

On Windows, run `install-windows.ps1` once. It validates the installation and creates a desktop shortcut. `update-windows.ps1` performs a safe fast-forward update and reruns verification.

## Private repositories

Set `GITHUB_TOKEN` in your environment. Never commit it to `.env` or source control.

```powershell
$env:GITHUB_TOKEN = 'your-fine-grained-token'
npm run promo -- --repo OWNER/PRIVATE-REPO
```

## Add local AI footage

1. Install [WanGP](https://github.com/deepbeepmeep/Wan2GP), or use the validated [Strix Halo ComfyUI toolbox](https://github.com/kyuz0/amd-strix-halo-comfyui-toolboxes) on Ryzen AI Max hardware.
2. Generate prompts after ingestion:

```bash
npm run ingest -- --repo edneycaleb-droid/fieldnote
node --import tsx scripts/wangp-prompts.ts --input public/generated/edneycaleb-droid-fieldnote.json
```

3. Render a generated clip as `public/generated/background.mp4`, then rerun ingestion and rendering:

```bash
npm run promo -- --repo edneycaleb-droid/fieldnote --background-video generated/background.mp4
```

Remotion renders all repository names, metrics, and copy; WanGP is restricted to text-free cinematic backgrounds because generative video models commonly distort typography.

## Automation

Run the **Render repository promo** workflow from GitHub Actions, enter any `OWNER/REPO`, and download the artifact. Public repositories work with the workflow token. For another private repository, provide a fine-grained token as a repository secret and adapt the workflow environment.

## Validation

```bash
npm run doctor
npm run typecheck
npm test
```

The CI workflow also performs a representative one-frame render to catch browser, bundling, and layout failures.

## Licensing note

This project code is intended for local use. WanGP and individual video models have separate licenses; confirm the selected model terms before commercial distribution.
