# Publish PREREQ

Version 2.1.0 · hosting documentation checked 17 September 2026.

**Recommended route: GitHub for the code, Render for the running Python app, and Cloudflare only when adding a custom domain.**

This is an ordinary website. It does not need a ChatGPT share link, ChatGPT login, OpenAI API key or a connection to this conversation. The ZIP contains application files and public catalog facts, not your chat history.

The repository and website are separate things. Uploading a ZIP to GitHub as a single file does not deploy an app. Upload the extracted source files.

## 1. Upload the project to GitHub

Choose ONE of these methods. Use a fresh extracted copy so that you do not upload a local cache or personal files by accident.

### Browser method: no Terminal installation

1. Extract `sabanci-prerequisite-graph-v2.1.zip` and open the inner `sabanci-prerequisite-graph` folder.
2. Sign in to GitHub. Choose **+ → New repository**. Name it `sabanci-prerequisite-graph`, choose **Public** to make the source public, and leave the automatic README, license and gitignore options unselected. Those files are already included.
3. Create the repository, then click **uploading an existing file**. In an existing empty repository, use **Add file → Upload files**.
4. Drag the CONTENTS of the extracted project folder onto the upload page, not the enclosing project folder and not the ZIP. On macOS, **Command + Shift + .** in Finder reveals dotfiles. Include `.github`, `.gitignore`, `.python-version` and `.dockerignore`. `.env.example` is a template, not a secret; never upload a real `.env`, `.cache`, `.git` or credentials.
5. Commit the upload to **main**. If GitHub offers a pull request instead, merge it into main. If your default branch has a different name, change `branch: main` in `render.yaml` to that exact name before deployment.
6. Check that the repository home page directly contains `render.yaml`, `gunicorn.conf.py`, `requirements-production.txt`, `prereq`, `web` and `docs`. They must not be one folder too deep.

GitHub supports browser file/folder uploads. This release is below its 100-file batch limit and its 25 MiB per-file limit. [1]

### Terminal alternative: uses the included publishing helper

With Git and the GitHub CLI already installed, open Terminal in the extracted project folder and run:

```bash
bash scripts/publish.sh
```

The helper opens GitHub authentication when needed, creates a **public** repository under your authenticated GitHub account and pushes the files. It refuses to overwrite an existing repository or an existing origin remote. It creates a GitHub no-reply commit identity if no Git identity is configured; review an existing configured identity before publishing. It does not create a website or charge for hosting. [2]

Do not run the helper after creating the same repository through the browser. Those are alternative methods, not two sequential steps.

## 2. Deploy the complete app on Render

The included `render.yaml` is a **free testing configuration**, not an always-on production promise. It creates one Python web service, not a static site, database service or paid disk. Review Render's deployment screen before approving anything.

1. Sign in to Render and connect GitHub. Grant access to this repository; access to unrelated repositories is not required.
2. Choose **New → Blueprint**. Connect `sabanci-prerequisite-graph`.
3. Name the Blueprint `prereq`. Select branch **main** and Blueprint Path **render.yaml**.
4. Review the proposed resources. Expect **one web service**, named `prereq`, with compute plan **Free**. If a paid resource is proposed unexpectedly, do not approve it.
5. Click **Deploy Blueprint**. Open the created web service and watch its Events/Logs until the deployment finishes.
6. Open the actual public URL shown by Render, for example `https://prereq-xxxx.onrender.com`. The assigned name may differ. This URL has no ChatGPT account identifier. You do not need to buy a domain. [3][4][5]

### Settings already supplied by this ZIP

| Setting | Value |
| --- | --- |
| Runtime | Python |
| Python line | 3.13, from `.python-version` |
| Build command | `pip install --no-cache-dir -r requirements-production.txt` |
| Start command | `gunicorn --config gunicorn.conf.py prereq.app:application` |
| Health path | `/health` |
| Server port | Render's `PORT` environment variable |
| Public URL scheme | `PREREQ_PUBLIC_SCHEME=https` |
| Temporary cache | `PREREQ_CACHE=/tmp/prereq/catalog.sqlite3` |
| Live checks enabled | `PREREQ_OFFLINE=0` |

Render accepts the minor version in `.python-version` and selects the matching patch release. The app automatically allows the exact hostname provided through `RENDER_EXTERNAL_HOSTNAME`. No wildcard hostname or manually guessed service address is needed. Custom domains must be added separately in section 5. [6][7]

The pinned public HTTPS scheme makes same-origin refresh work behind Render's HTTP connection from its TLS terminator, without trusting arbitrary incoming forwarded headers. This code path has local regression tests; it has not yet been tested in a real Render account.

### Manual fallback when not using Blueprints

Use **New → Web Service → Git Provider → your repository**, not Static Site. Set Language to **Python 3**, branch to main and leave Root Directory empty. Copy the build/start commands and environment values above, set Health Check Path to `/health`, and choose Free for a first test. There is a Dockerfile in the repository, so explicitly select Python when following this native-runtime path. [5]

Do not deploy both paths; that creates two separate services.

## 3. Check the hosted website before sharing it widely

Opening the site and seeing a graph is not enough to prove live catalog access.

Open EE / Fall 2024 as a UI test. The initial map must contain only the five collapsed section headings. Opening a heading must not auto-open course branches. Expanding or collapsing a branch must preserve the camera. Refreshing/reopening the site should restore your chosen major and saved markers, but leave branches closed.

Then test a different supported major/admission-term combination that is actually present in the university catalog. It must retrieve its own requirements, never substitute the EE snapshot. Check **Sources**: look for a successful verification date and no source error. Open a course detail not in the bundled records and compare its prerequisites/corequisites against its official source. Observe the prerequisite coverage counter as indexing progresses. A **Snapshot** label by itself is not evidence of a successful live check.

Open `https://YOUR-ACTUAL-HOST/health`. A successful response should report:

```json
{"status":"ok","version":"2.1.0"}
```

This endpoint checks the application process, not the university connection or the completeness of the data.

**Current validation limit:** the included offline data is still EE / Fall 2024 with 57 detail records. The build environment could not resolve the university's hostname. Live checks from the eventual hosting network, complete indexing, cross-major parser validation, the Render deploy itself and custom DNS remain unverified. No update to the startup UI changes that boundary.

Catalog checks are demand-driven and use a 12-hour cache policy. They are not a promise that an idle site polls the university continuously. Unknown or failed checks retain honest source status rather than producing guessed prerequisite edges.

## 4. Keep the catalog cache and avoid free-tier sleep

**Free is suitable for a first deployment test.** Render currently sleeps a free service after 15 minutes without incoming traffic. Waking takes roughly a minute. The local filesystem, including the fetched SQLite cache, is lost on sleep, restart or redeploy; free services cannot attach a persistent disk. The app falls back to the bundled data and fetches again. Usage limits also apply. [8]

For a more durable public deployment, use a **paid web-service instance plus a persistent disk**. A paid instance without a disk still does not preserve the cache across redeploys. Check the displayed prices before approving either resource. [9]

For a Blueprint-managed service, update the existing root `render.yaml` rather than making conflicting dashboard-only changes. Keep the same service name and all other settings:

Change:

```yaml
    plan: free
```

to:

```yaml
    plan: 0.5c-512mb
    disk:
      name: catalog-cache
      mountPath: /var/data
      sizeGB: 1
```

Then change the existing PREREQ_CACHE value to:

```yaml
      - key: PREREQ_CACHE
        value: /var/data/prereq/catalog.sqlite3
```

The paid plan ID above is the currently documented 0.5 CPU / 512 MB instance. Review its displayed price before proceeding. [4]

Commit the change and review/sync the existing Blueprint. This step intentionally switches to billable hosting. Do not create a second Blueprint for the same service. The new cache starts empty; it will populate from successful source checks. Only files below the disk mount path persist. [3][9]

Keep **one Gunicorn worker and one service instance** in this version. Source pacing and index-job coordination are process-local. Increasing workers or replicas requires a shared coordinator first. A durable disk does not remove application bugs or guarantee university availability.

## 5. Add a domain through Cloudflare, optionally

The `onrender.com` address is already public and independent of ChatGPT. A domain you own is optional.

Use a dedicated subdomain, for example `courses.example.com`, to avoid disturbing an existing website or email. `example.com` is a placeholder, not a domain provided with this release. Your domain must already use Cloudflare DNS; otherwise follow your registrar/Cloudflare domain-onboarding process first.

1. In Render, open the web service → **Settings → Custom Domains → Add Custom Domain**. Add `courses.example.com`.
2. In Render → **Environment**, add **PREREQ_HOSTS** with value `courses.example.com`. Use comma-separated exact hostnames for more than one. No `https://`, path or wildcard. Save and redeploy. The assigned Render hostname remains automatically allowed. Include every custom hostname you verify: Render may use any verified custom domain as the Host header for health checks. [15] This environment variable is not present in the Blueprint, so adding it in the dashboard does not conflict with a Blueprint-defined value.
3. In Cloudflare → your domain → **DNS → Records**, add a record:

| Field | Value |
| --- | --- |
| Type | CNAME |
| Name | `courses` |
| Target | Your actual `prereq-xxxx.onrender.com` hostname, without `https://` |
| Proxy status | **DNS only**, the gray cloud |
| TTL | Auto |

4. Remove/replace only conflicting A/AAAA/CNAME records for this exact subdomain. Do not remove unrelated DNS or mail records.
5. Return to Render's Custom Domains section and click **Verify**. Wait until its certificate is issued and valid. Open the new HTTPS address and test refresh. [10][11]

Leaving the record DNS-only is the simplest setup. Cloudflare is then your DNS provider; Render serves the app and HTTPS. After the Render certificate is valid, optional Cloudflare proxying can be enabled. For proxying, use **SSL/TLS → Full (strict)**, not Flexible, and avoid cache rules that override the app's no-store headers on `/api/*`. Re-test source refresh. [11][12]

Before switching from an offline file or a temporary hostname, use **My plan → Export JSON**. Import that file on the final domain. Plans are browser-local and are not automatically moved between different site origins.

## 6. Publish future updates

With the GitHub-connected deployment, commits to the linked branch trigger builds. A failed build leaves the previous successful deployment in place. [5]

From a local clone, review changes first and then run:

```bash
git status
python3 -m unittest discover -s tests -v
node --test tests/model.test.cjs
python3 scripts/build_preview.py
git add .
git commit -m "Update PREREQ"
git push origin main
```

Node is needed only for the JavaScript tests, not for serving the app. Do not upload a real environment file, local database, access token or transcript. Keep your published branch and Render logs accessible so a failed update can be diagnosed or rolled back.

## 7. Cloudflare Pages / GitHub Pages: snapshot only

Neither static deployment below runs this Python server. Cloudflare supports other runtimes, but the current Gunicorn/SQLite/background-thread app is not a drop-in Worker. A Worker-native version would require changes to the backend and storage, not simply uploading this ZIP. [13][14]

For an explicitly offline public preview on GitHub Pages: **Settings → Pages → Deploy from a branch → main → /docs → Save**.

For an explicitly offline public preview on Cloudflare Pages: import the Git repository, use framework **None**, build command `exit 0`, and output directory **docs**. The resulting Pages URL serves the bundled preview. [13]

Do not advertise either snapshot as the live catalog service. The Render path above serves `web/index.html` and the API together, while `docs/index.html` is deliberately offline.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Blueprint cannot find files | `render.yaml` and the source folders must be at repository root. |
| Build cannot find Gunicorn | Use `requirements-production.txt`, not the empty local-development setup. |
| No open port detected | Use the supplied Gunicorn start command, not `python3 start.py`. |
| Host is not allowed | Add the exact custom hostname to `PREREQ_HOSTS`. Do not use `*`. |
| Refresh returns Origin mismatch | Keep `PREREQ_PUBLIC_SCHEME=https` on the hosted service and use HTTPS. |
| Only the EE snapshot appears | Inspect Sources and Render logs for DNS/TLS/robots/parser errors. Do not disable access protections. |
| Slow first visit or cache disappears | Free-tier sleep and ephemeral storage; see section 4. |
| Empty personal plan after changing URL | Import the JSON exported from the previous origin. |
| API returns 429 during a group test | Current rate limiting is per socket peer. A managed proxy can aggregate visitors. Validate the host's trusted-client-IP path before adjusting rate limits; do not trust arbitrary forwarded headers. |

For a self-managed container host, `docker compose up --build -d` still works. Set `PREREQ_HOSTS` and, behind HTTPS, `PREREQ_PUBLIC_SCHEME=https` in `.env`. The supplied host port is loopback-only; a reverse proxy supplies HTTPS. Read SECURITY.md before public exposure. The Docker image and real hosting account were not exercised in this build environment.

## Official references

[1] GitHub browser uploads: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository

[2] GitHub CLI repository creation: https://cli.github.com/manual/gh_repo_create

[3] Render Blueprints and setup: https://render.com/docs/infrastructure-as-code

[4] Render Blueprint field reference: https://render.com/docs/blueprint-spec

[5] Render web services, ports and deployment: https://render.com/docs/web-services

[6] Render Python versions: https://render.com/docs/python-version

[7] Render-provided environment variables: https://render.com/docs/environment-variables

[8] Render free-instance limits: https://render.com/docs/free

[9] Render persistent disks: https://render.com/docs/disks

[10] Render custom domains: https://render.com/docs/custom-domains

[11] Render with Cloudflare DNS: https://render.com/docs/configure-cloudflare-dns

[12] Cloudflare Full (strict): https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/

[13] Cloudflare Pages static HTML: https://developers.cloudflare.com/pages/framework-guides/deploy-anything/

[14] GitHub Pages static hosting: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages

[15] Render health-check hostnames: https://render.com/docs/health-checks

Hosting UI and pricing can change. Review the actual confirmation screen; this guide does not authorize a purchase or certify a live deployment.
