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

- Disk: **20 GB gp3** is ample — ephemeral mode keeps the local footprint near-zero.
- Only reel-slot games (1M+ sims + Rust optimizer) would need more cores.

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
