# GitHub and hosting

## Create the repository

This archive has not been uploaded automatically. The connected GitHub interface in the build session allowed reading, not creating repositories or pushing files.

Install Git and the GitHub CLI using their official installation instructions. From this folder, run:

```sh
bash scripts/publish.sh
```

The helper authenticates through the GitHub CLI, creates a **public** `sabanci-prerequisite-graph` repository in the authenticated account and pushes the source. It never asks you to paste a token into the project. It stops when the repository or origin remote already exists and never force-pushes. The actual public username comes from the active GitHub CLI login, not a hard-coded account.

A different repository name can be supplied as the first argument. For Windows, use Git Bash or the equivalent explicit commands:

```sh
gh auth login
git init -b main
git add .
git commit -m "Build Sabanci prerequisite graph"
gh repo create sabanci-prerequisite-graph --public --source=. --remote=origin --push
```

Configure your Git commit identity first if Git requests it. Review `git status` before committing. `.cache`, environment files, Python caches and local logs are excluded by `.gitignore`.

GitHub publication and public website hosting are different operations. The provided CI workflow runs tests and verifies generated snapshots; it has read-only repository permissions and does not deploy the service.

## Publish the offline preview on GitHub Pages

`docs/index.html` is already a complete standalone **offline** version. In the repository, choose **Settings → Pages → Deploy from a branch → main → /docs → Save**. This publishes the snapshot preview only. It does not run Python, check new majors or update from Sabancı. Do not describe the Pages URL as the live catalog service.

## Run the live app in a container

Use a host capable of running a persistent Python/container service. First verify that its network can reach the public SUIS catalog and that automated access is allowed. Build and start:

```sh
cp .env.example .env
# Edit PREREQ_HOSTS in .env to include your actual public hostname.
docker compose up --build -d
```

The provided port mapping is loopback-only on the server (`127.0.0.1:8765`). Put an HTTPS reverse proxy in front of it. Serve the app at the domain root. Preserve Host, pass the correct forwarded protocol from a trusted proxy, and configure Gunicorn to trust only that proxy address. An incorrect scheme/Host configuration can cause an intentional 403 on refresh.

The image uses one Gunicorn worker, eight HTTP threads, a non-root user, read-only application code and a persistent `/data` cache volume. The service needs outbound DNS and HTTPS to `suis.sabanciuniv.edu`; a forced enterprise HTTP proxy is not supported by the fixed-origin client. Do not remove TLS validation or public-IP checks to work around a failed fetch.

Use `/health` for a process-health probe. This endpoint does not assert that Sabancı is reachable or the catalog fresh. Check Sources in the UI and run `scripts/check_live.py` separately for source validation. The first real degree fetch loads the term selector, degree page and referenced elective pools. The shared prerequisite index then reads course pages progressively, prioritizing University and Required courses. Individually opened course panels can also request a detail check. The first full index is not instantaneous.

Add request limits, monitoring and sensible log retention at the reverse proxy. Do not scale this version to multiple workers or replicas without distributed upstream pacing. Public hosting may have service costs; no hosting account, domain, paid service or deployment was created in this build.

## Release checks

Run unit/model/browser tests, then verify at least one real current degree in each supported page-layout family: engineering with linked pools; Psychology with its extra Philosophy requirement; a split-core program; Management. Confirm that the chosen admission term is available. Compare the displayed course counts and summary against the official pages. Confirm unknown consent conditions remain unknown, test a temporary source outage, and verify the exact public HTTPS Host/Origin setup.

The Docker recipe, GitHub publication helper and CI/Pages deployment instructions are supplied but were not executed against a live hosting account during this build.

## Official references

GitHub CLI repository creation: https://cli.github.com/manual/gh_repo_create

GitHub Pages static hosting: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages

Gunicorn production server release history: https://gunicorn.org/2026-news/

GitHub Actions checkout is pinned to commit `d23441a48e516b6c34aea4fa41551a30e30af803`, resolved from the official `actions/checkout` v6 tag on 17 September 2026. Audit dependency updates rather than changing immutable pins blindly.
