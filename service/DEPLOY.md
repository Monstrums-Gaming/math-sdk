# Deploying the build service (Laravel Forge + AWS EC2)

The build service is a **pure-Python FastAPI** app. Mystery-box games disable the Rust
optimizer, so the server needs **no Cargo/Rust** — just Python ≥ 3.12 and the venv.

It is designed to sit next to a Laravel backoffice: the backoffice makes HTTP calls
(`POST /manifests` / `POST /builds`, poll `GET /builds/{id}`), and in ephemeral mode the
build lands in S3 and the API returns stable `s3_files[].url`s that the backoffice stores.

---

## EC2 sizing

Bursty CPU, light RAM, tiny disk (ephemeral mode deletes local output after upload). A
100k-sim mystery-box build takes only seconds, and these games use `num_threads=1`.

| Use | Instance | Notes |
|-----|----------|-------|
| Build service only | **t3.medium** (2 vCPU, 4 GB) | Good default; cheap, burstable. |
| Frequent/back-to-back builds | **c6i.large / c7g.large** | Non-burstable — no t3 CPU-credit throttling. |
| Colocated with the backoffice | **t3.large** (2 vCPU, 8 GB) | Extra RAM for PHP-FPM + MySQL + the service. |

### Recommended production (dedicated, mystery-box only)

**`t4g.medium` (2 vCPU, 4 GB, Graviton/arm64), 30 GB gp3, dedicated instance.**

- **arm64 is required** — the CI builds `--platform linux/arm64`, so prod must be Graviton
  (`t4g`/`c7g`), same as staging. An amd64 box fails with `exec format error`.
- **Burstable is fine**: a backoffice "create a box" flow is low-volume and each 100k-sim
  build is a ~2.5 s CPU burst — t-family credits cover it. Move to **`c7g.large`**
  (non-burstable) only if you'll do frequent back-to-back builds and hit CPU-credit
  throttling (watch CloudWatch `CPUCreditBalance`).
- **Dedicated, not colocated** for prod: isolation means a build can never starve the
  backoffice (on staging they share a box, which is fine at low volume).
- **Disk 30 GB** (not 20): ephemeral mode keeps the app footprint near-zero, but leave
  headroom for Docker images + build cache (see "Housekeeping" below).
- Prefer an **EC2 IAM role** (`s3:PutObject` + `GetObject`/`HeadObject` on the bucket) over
  static keys in `.env`; with the container, remember the IMDSv2 hop-limit = 2 gotcha.
- Only **reel-slot games** (1M+ sims + Rust optimizer) would need more cores (`c7g.xlarge`+)
  and Rust installed — not applicable to a mystery-box-only service.

### Housekeeping — prune Docker weekly

Every image rebuild/pull leaves **reclaimable** layers and build cache; left alone they fill
the disk and Docker Desktop/daemon gets sluggish under disk pressure. The CI deploy already
runs `docker system prune -af` before each pull, so a **frequently-deployed** box stays clean
— but add a weekly cron as a safety net for quiet periods (and for local dev boxes, where
repeated `docker build` piles up cache fast).

Create `/etc/cron.d/docker-prune` (Ubuntu; runs as root, Sundays 04:00):

```cron
# Weekly Docker cleanup — reclaim unused images + build cache older than 7 days.
# `until=168h` keeps the current deploy's image; the running container is always protected.
0 4 * * 0 root docker system prune -af --filter "until=168h" >> /var/log/docker-prune.log 2>&1
```

Then `sudo chmod 644 /etc/cron.d/docker-prune`. Verify it parses: `sudo run-parts --test
/etc/cron.d 2>/dev/null; cat /var/log/docker-prune.log` after the first run. On macOS/local
dev there's no `cron.d`; run it by hand periodically instead:
`docker builder prune -f && docker image prune -f` (avoid `-a` locally if Docker Hub is flaky,
so the base image isn't dropped and re-pulled).

> Why `--filter "until=168h"` and not a bare `prune -af`: it only removes objects older than a
> week, so an in-flight or just-deployed image is never touched. The running `mbs` container
> and its image are protected regardless.

---

## The one hard rule: a single worker

Job state is **in-memory**, so run **exactly one** server process. Multiple workers would
not share the job registry — `GET /builds/{id}` on worker B wouldn't find a job created on
worker A. One worker is plenty; the in-process `MAX_CONCURRENT_BUILDS` thread pool handles
concurrency. So: `uvicorn …` with **no** `--workers`, or `gunicorn -w 1`.

---

## Forge setup

Forge manages a plain Ubuntu box, so the service runs as a **Daemon** behind (optionally)
an Nginx reverse-proxy.

### 1. Provision

- Create a server in Forge on your AWS account. Use **Ubuntu 24.04** (ships Python 3.12).
  On 22.04, install 3.12 via the deadsnakes PPA first.

### 2. Get the code + install

```sh
cd /home/forge
git clone <your-repo> math-sdk && cd math-sdk
git checkout <branch>
make setup            # creates ./env, installs requirements.txt (fastapi/uvicorn incl.)
```

### 3. Configure env

Create `/home/forge/math-sdk/.env` (the service loads it via python-dotenv — separate from
Laravel's `.env`). Copy `.env.example` and fill in:

```sh
cp .env.example .env
# required: API_KEY=<long random secret>
# S3 (ephemeral on by default when a bucket is set):
#   AWS_S3_BUCKET, S3_PREFIX, AWS_REGION, AWS_ACCESS_KEY_ID/SECRET (or an IAM role)
#   S3_PUBLIC_BASE_URL=<CDN domain>   # so returned url is your public/CDN URL
```

> Prefer an **EC2 IAM role** with `s3:PutObject` (+ `s3:GetObject`/`HeadObject`) on the
> bucket over static keys in `.env` — then omit `AWS_ACCESS_KEY_ID`/`SECRET` and boto3 uses
> the role automatically.

### 4. Run as a Forge Daemon

Server → **Daemons** → New Daemon:

```
Command:   /home/forge/math-sdk/env/bin/uvicorn service.app:app --host 127.0.0.1 --port 8000
Directory: /home/forge/math-sdk
User:      forge
```

(Or `…/env/bin/gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8000 service.app:app`.)
Forge keeps it running and restarts it on crash/deploy.

### 5. Expose it — pick one

- **Localhost only (recommended):** leave it bound to `127.0.0.1:8000` and have Laravel call
  `http://127.0.0.1:8000` on the same box. Not publicly reachable; the API key is defence in
  depth. Nothing else to configure.
- **Public subdomain:** add a Forge site `builds.yourdomain.com`, enable Let's Encrypt TLS,
  and replace its Nginx `location /` with a proxy:
  ```nginx
  location / {
      proxy_pass http://127.0.0.1:8000;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_read_timeout 300;   # a prod build can take a while
  }
  ```

### 6. Deploy script (if using a Forge site pipeline)

```sh
cd /home/forge/math-sdk
git pull origin <branch>
env/bin/pip install -r requirements.txt
# restart the daemon (Forge does this automatically, or:)
# sudo supervisorctl restart daemon-<id>:*
```

---

## Alternative: manual deploy on EC2 with Docker

Prefer a container to a Forge daemon? The repo ships `service/Dockerfile` (single uvicorn
worker, boto3 included). No Rust needed.

### 1. Launch the instance

- **AMI:** Ubuntu 24.04 · **Type:** t3.medium (see sizing) · **Disk:** 20 GB gp3.
- **Security group:** SSH (22) from your IP. Expose the app port (8000) only if the
  backoffice is off-box; if Laravel is on the same instance/VPC, keep 8000 closed and call
  it privately.
- **IAM role (recommended):** attach an instance role with `s3:PutObject` +
  `s3:GetObject`/`s3:HeadObject` on the bucket, so you don't put AWS keys in `.env`.

### 2. Install Docker

```sh
sudo apt-get update && sudo apt-get install -y docker.io git
sudo usermod -aG docker ubuntu   # log out/in so `docker` works without sudo
```

### 3. Build the image

```sh
git clone <your-repo> math-sdk && cd math-sdk
git checkout <branch>
docker build -f service/Dockerfile -t mysterybox-build-service .   # context = repo root
```

### 4. Provide config at runtime (never bake secrets into the image)

Create `/home/ubuntu/math-sdk/.env` (from `.env.example`) with `API_KEY`, `AWS_S3_BUCKET`,
`S3_PREFIX`, `AWS_REGION`, `S3_PUBLIC_BASE_URL`, etc. With an IAM role, **omit**
`AWS_ACCESS_KEY_ID`/`SECRET` — boto3 uses the role. Otherwise set them.

> ⚠️ **No inline comments on value lines in a `--env-file`.** Docker (unlike python-dotenv)
> does **not** strip them — `AWS_S3_BUCKET=juice-cdn   # my bucket` sets the bucket to the
> literal `juice-cdn   # my bucket`, silently breaking S3 (deploy skipped/failed). Keep
> comments on their own `#` lines. Verify what the container actually resolved:
> ```sh
> docker exec mbs python -c "from service.config import settings; print(repr(settings.AWS_S3_BUCKET))"
> ```

### 5. Run

```sh
docker run -d --name mbs --restart unless-stopped \
  -p 8000:8000 \
  -v mbs-data:/app/service/artifacts \
  --env-file /home/ubuntu/math-sdk/.env \
  mysterybox-build-service
```

- **Job status is SQLite** (`ARTIFACT_DIR/jobs.db`) and survives a *process* restart on its
  own. To also survive a **container recreate** (every CI deploy replaces the container),
  mount `ARTIFACT_DIR` on a named volume as above (`-v mbs-data:/app/service/artifacts`) —
  otherwise `GET /builds/{id}` loses history on each deploy (the backoffice still has the saved
  S3 URLs, so it's degraded, not broken). The volume is tiny (SQLite + per-job manifest/log).
- **Ephemeral mode** (bucket set) → build *output* goes to S3 and local output is deleted, so
  the volume only holds the small `jobs.db` + logs. With `EPHEMERAL_BUILDS=false` the same
  volume also keeps the publish zips across restarts.
- Health check: `curl http://localhost:8000/healthz` → `{"status":"ok"}`. Logs:
  `docker logs -f mbs`.

### IMDSv2 gotcha (IAM role from inside a container)

By default the instance metadata hop limit is 1, which **blocks Docker containers** from
reaching the IAM role credentials (IMDSv2). Either raise the hop limit to 2, or fall back to
static keys in `.env`.

```sh
# raise hop limit so the container can use the instance role
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
aws ec2 modify-instance-metadata-options --instance-id "$IID" \
  --http-put-response-hop-limit 2 --http-endpoint enabled --region <region>
```

### Same box as the Forge backoffice (recommended)

Forge runs Laravel natively (Nginx + PHP-FPM on 80/443); the service runs as a Docker
container beside it. They don't collide — the container just needs to be reachable from
Laravel over **loopback only**.

- **Bind the container to `127.0.0.1`**, not `0.0.0.0`, so it is never publicly exposed and
  you don't touch the security group / ufw:
  ```sh
  docker run -d --name mbs --restart unless-stopped \
    -p 127.0.0.1:8000:8000 \
    --cpus 2 --memory 2g \
    --env-file /home/forge/math-sdk/.env \
    mysterybox-build-service
  ```
- **`--cpus` / `--memory`** cap a build so it can't starve PHP-FPM/MySQL on the shared box.
  Combine with `MAX_CONCURRENT_BUILDS` in `.env`.
- **Laravel calls `http://127.0.0.1:8000`** with the API key — no Forge Nginx site, no TLS,
  no public port. Example `config/services.php`:
  ```php
  'mathsdk' => [
      'url' => env('MATHSDK_URL', 'http://127.0.0.1:8000'),
      'key' => env('MATHSDK_KEY'),
  ],
  ```
- **Two separate deploy lifecycles:** Forge's git pipeline deploys Laravel; the container is
  updated independently (§7 below). They share the host, not the release process.
- **Two separate `.env` files:** Laravel's (Forge-managed, in the site dir) and the
  service's (`/home/forge/math-sdk/.env`, passed via `--env-file`). Keep them distinct.
- Size the box for both (t3.large / 8 GB — see sizing). Install Docker manually per §2;
  Forge won't manage it, but it runs fine alongside Forge's stack.

#### Adding it to an *existing, running* Forge box

Safe to do live — the container is isolated from Forge's stack (different ports, own
process). But on a production box, mind three things:

1. **Check headroom first.** The box was sized for the backoffice. Run `free -h`, `nproc`,
   `uptime`. If RAM is tight, a build can push MySQL into swap. Cap the container
   (`--cpus`, `--memory`) and set `MAX_CONCURRENT_BUILDS=1`; resize the instance
   (stop → change type → start) if it's already near capacity.
2. **Docker bypasses ufw.** Publishing a port to `0.0.0.0` opens it *even if ufw would
   block it* — a real exposure risk on a box managed by Forge's firewall. **Binding to
   `127.0.0.1` (as above) avoids this entirely** — nothing is published beyond loopback.
   Never publish `-p 8000:8000` (all interfaces) here.
3. **IAM role for S3** can be attached to the **already-running** instance without a reboot
   (Actions → Security → Modify IAM role). Then the container uses it (remember IMDSv2
   hop-limit = 2).

Rollback is clean: `docker rm -f mbs` removes the service with zero effect on the Laravel
app. Forge's deploy pipeline and OS updates never touch the container.

### 6. TLS / public access (optional)

If the service must be reachable off-VPC, front it with an **ALB + ACM cert**, or run a
`caddy`/`nginx` container that terminates TLS and proxies to `mbs:8000`. For a same-VPC
backoffice, skip this — call `http://<private-ip>:8000` with the API key. See
**"Custom domain + HTTPS"** below for a concrete custom-domain setup.

---

## Custom domain + HTTPS

To call the service over `https://<your-domain>` with a real cert (e.g. so a Laravel app on
another host — or a browser tool — reaches it): terminate TLS at a reverse proxy on a
hostname you own, and keep `mbs` plain HTTP behind it (bound to `127.0.0.1:8000`, never
exposed directly). Example hostnames: `staging.builds.theboxforge.com` (staging),
`builds.theboxforge.com` (prod).

**Prereqs (both paths):** a DNS **A record** for the hostname → the box's public IP, and the
security group allowing inbound **80 + 443**.

**Which path?** It comes down to whether ports 80/443 are already taken on the box. Check:
```sh
sudo ss -ltnp '( sport = :443 or sport = :80 )'   # anything listening on 80/443?
```

### Path A — the box already runs nginx / Forge on 80/443 (recommended for the staging box)

The staging box runs the Forge backoffice, so **nginx already owns 80/443** — don't add
Caddy (it can't bind those ports). Reuse the existing edge as the proxy:

1. **Forge → New Site**, domain `staging.builds.theboxforge.com`, "no application" /
   static — you only want its nginx vhost.
2. **Obtain the cert FIRST, on the default config.** Forge → SSL → **Let's Encrypt**. Do this
   *before* adding the proxy: Let's Encrypt's HTTP-01 challenge hits
   `http://…/.well-known/acme-challenge/…` over port 80, and Forge's own default config serves
   that token. (Needs DNS → the box and inbound 80 open. If the record is behind Cloudflare's
   proxy, grey-cloud it to DNS-only first, or the challenge 404s at Cloudflare's edge.)
3. **Only after the cert is active**, edit the site's Nginx config → replace the
   `include forge-conf/<id>/site.conf;` line with a proxy to the local service:
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_read_timeout 300;   # a prod build can take a while
   }
   ```
   > Do **not** add a `location ^~ /.well-known/acme-challenge/ {…}` carve-out on a Forge box —
   > Forge re-injects its own (more-specific) challenge location on each renewal, so it wins
   > over `location /` automatically. A `^~` carve-out pointing at the site's `public/`
   > overrides Forge's handler and makes issuance/renewal 404.
4. `mbs` stays exactly as deployed (`-p 127.0.0.1:8000:8000`) — the CI redeploy is unchanged;
   nginx reaches it over loopback. No Docker-network or workflow changes.

Plain-nginx (non-Forge) equivalent: create the vhost by hand and run `certbot --nginx -d
staging.builds.theboxforge.com`.

### Path B — a standalone Docker box with 80/443 free → Caddy

If nothing owns 80/443, the repo ships **[`service/Caddyfile`](Caddyfile)** — Caddy fetches +
renews a Let's Encrypt cert automatically. Run it with **host networking** so it binds 80/443
and reaches `mbs` at `127.0.0.1:8000` (which survives every CI redeploy — no docker-network to
re-attach):
```sh
docker run -d --name mbs-proxy --restart unless-stopped --network host \
  -v /home/ubuntu/math-sdk/service/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data caddy:2
```
(Edit the site address in the `Caddyfile` per environment.)

### Then point the caller at it

In the backoffice `.env`: `MATHSDK_URL=https://staging.builds.theboxforge.com` (full
cert verification — no `verify=false`; it's a real cert). The API key still travels in the
`X-API-Key` header. This also resolves the *"`cURL error 7` from a containerized Laravel"*
problem — the app just calls the public HTTPS URL instead of an unreachable `localhost:8000`.

> **Local dev caveat:** a real Let's Encrypt cert needs the host publicly reachable (or DNS-01).
> A local Mac-mini dev box usually can't get one — keep local on `http://mbs:8000` over a
> shared Docker network (see [`BACKOFFICE_INTEGRATION.md`](BACKOFFICE_INTEGRATION.md)) and
> reserve the custom HTTPS domain for the deployed staging/prod boxes.

### 7. Update

```sh
cd math-sdk && git pull
docker build -f service/Dockerfile -t mysterybox-build-service .
docker rm -f mbs
docker run -d --name mbs --restart unless-stopped -p 8000:8000 \
  --env-file .env mysterybox-build-service
```

> Production tip: build the image in CI and push to **ECR**, then `docker pull` on the box —
> reproducible and faster than building on the instance. Full step-by-step (ECR + GitHub
> Actions OIDC + SSM deploy) in **[`CICD.md`](CICD.md)**.

---

## Mixing with the backoffice

| Topology | When | How |
|----------|------|-----|
| **Same server** (recommended) | Low/normal volume | Laravel + the service daemon on one box; service bound to `127.0.0.1`, Laravel calls it over localhost. Cheapest, most secure. A heavy build shares CPU — bounded by `MAX_CONCURRENT_BUILDS`. |
| **Separate build server** | Frequent/heavy builds | Dedicated instance; Laravel calls it over the private VPC or a TLS subdomain. Full isolation. |

### The clean seam

- Laravel `POST /manifests?build=true&mode=prod` → gets `job_id`.
- Laravel polls `GET /builds/{job_id}` until `status=succeeded`.
- Ephemeral mode uploads to S3 and returns `s3_files[].url` → **Laravel stores those URLs**
  against the box in its own DB. The build server stays stateless; S3 holds the artifacts.

Because Laravel records the S3 URLs, the in-memory job registry losing history on restart
is usually a non-issue. If you need durable job history in the service itself, that's the
SQLite upgrade noted in `README.md`.

### Example Laravel call (Guzzle)

```php
$res = Http::withHeaders(['X-API-Key' => config('services.mathsdk.key')])
    ->baseUrl('http://127.0.0.1:8000')
    ->post('/manifests?build=true&mode=prod', $boxSpec)   // simplified box fields
    ->json();
$jobId = $res['job']['job_id'];
// …poll GET /builds/{$jobId}; on success, persist $status['s3_files'] urls.
```
