# Backoffice integration (Laravel) — calling the build service

You already have mystery box + prize models. This is **only the integration**: how to hand a
box to the build service, track the build, and store the resulting S3 file URLs. It does not
introduce a new box module — it plugs into your existing one.

The service runs as a container on the **same server**, bound to `127.0.0.1:8000`, so Laravel
calls it over loopback with an API key. API reference: [`API.md`](API.md).

---

## The flow

```
Your existing "publish/build box" action
   ─▶ POST /manifests?build=true&mode=prod   (maps your box → a manifest, returns job_id)
   ─▶ poll GET /builds/{job_id} until status = succeeded
   ─▶ save game_id + s3_files[].url onto your box record
```

Build is async (seconds to a minute+): fire it, then **poll from a queued job** — never in the
web request.

---

## 1. Config

`.env`:
```
MATHSDK_URL=http://127.0.0.1:8000
MATHSDK_KEY=the-same-API_KEY-that-is-in-the-container-.env
```
`config/services.php`:
```php
'mathsdk' => [
    'url' => env('MATHSDK_URL', 'http://127.0.0.1:8000'),
    'key' => env('MATHSDK_KEY'),
],
```

---

## 2. API client — `app/Services/MathSdk.php`

```php
<?php

namespace App\Services;

use Illuminate\Http\Client\PendingRequest;
use Illuminate\Support\Facades\Http;

class MathSdk
{
    protected function client(): PendingRequest
    {
        return Http::baseUrl(config('services.mathsdk.url'))
            ->withHeaders(['X-API-Key' => config('services.mathsdk.key')])
            ->acceptJson()
            ->timeout(30);
    }

    /** Assemble a manifest from simplified box fields and start a build. */
    public function assembleAndBuild(array $boxSpec, string $mode = 'prod', bool $overwrite = true): array
    {
        return $this->client()
            ->post("/manifests?build=true&mode={$mode}&overwrite=".($overwrite ? 'true' : 'false'), $boxSpec)
            ->throw()
            ->json();
    }

    /** Poll a build job's status. */
    public function getBuild(string $jobId): array
    {
        return $this->client()->get("/builds/{$jobId}")->throw()->json();
    }
}
```

---

## 3. Add build-tracking columns to your existing box table

Additive migration — no new table:
```php
Schema::table('mystery_boxes', function (Blueprint $t) {   // ← your existing table name
    $t->string('game_id')->nullable();
    $t->string('build_job_id')->nullable();
    $t->string('build_status')->default('idle');   // idle|building|succeeded|failed
    $t->text('build_error')->nullable();
    $t->decimal('rtp', 6, 4)->nullable();          // returned by the service
    $t->json('s3_files')->nullable();              // [{name,key,uri,url}, ...] — the publish files
});
```

---

## 4. Trigger from your existing flow

Wherever you currently finalize/publish a box, dispatch the build (don't build inline):
```php
use App\Jobs\BuildMysteryBox;

// inside your existing controller/service after the box is saved:
$box->update(['build_status' => 'building']);
BuildMysteryBox::dispatch($box->id);
```
Add a "Build / Rebuild" button in your box admin that hits this. Requires a running queue
worker (Forge → site → **Queue**).

---

## 5. The job — map your box → spec, build, poll, save

`app/Jobs/BuildMysteryBox.php`:
```php
<?php

namespace App\Jobs;

use App\Models\MysteryBox;               // ← your existing model
use App\Services\MathSdk;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;

class BuildMysteryBox implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 600;

    public function __construct(public int $boxId) {}

    public function handle(MathSdk $sdk): void
    {
        $box = MysteryBox::with('prizes')->findOrFail($this->boxId);

        // ── MAP your existing box + prizes to the service's box spec ──────────────
        // Adjust the field names on the right to match YOUR schema.
        $spec = [
            'game_name'       => $box->name,                    // your box name
            'provider_number' => (int) config('services.mathsdk.provider_number', 3), // your real ACP studio id
            'provider_name'   => 'monstrum',
            'box_cost'        => (float) $box->price,           // your price/box_cost field
            'cost_model'      => 'unit',                        // ACP-valid
            'prizes'          => $box->prizes->map(fn ($p) => [
                'name'   => $p->name,                           // your prize label
                'payout' => (float) $p->payout,                 // your catalog value/multiplier
                'prob'   => (float) $p->probability,            // your odds — see note below
            ])->values()->all(),
        ];
        // ──────────────────────────────────────────────────────────────────────────

        try {
            $res   = $sdk->assembleAndBuild($spec, mode: 'prod', overwrite: true);
            $jobId = $res['job']['job_id'];
            $box->update(['build_job_id' => $jobId, 'game_id' => $res['game_id'], 'rtp' => $res['rtp']]);
        } catch (\Throwable $e) {
            // 400 = bad odds/economics (RTP >= 1.0, probs != 1.0, non-integral quotas)
            $box->update(['build_status' => 'failed', 'build_error' => $e->getMessage()]);
            return;
        }

        for ($i = 0; $i < 60; $i++) {
            sleep(5);
            $s = $sdk->getBuild($jobId);
            if ($s['status'] === 'succeeded') {
                $box->update(['build_status' => 'succeeded', 's3_files' => $s['s3_files']]);
                return;
            }
            if ($s['status'] === 'failed') {
                $box->update(['build_status' => 'failed', 'build_error' => $s['error'] ?? 'build failed']);
                return;
            }
        }
        $box->update(['build_status' => 'failed', 'build_error' => 'build timed out']);
    }
}
```

---

## 6. The result

On success, `$box->s3_files` holds the stable publish-file URLs:
```json
[
  { "name": "index.json",             "url": "https://juice-cdn.s3.ap-southeast-2.amazonaws.com/math-sdk/staging/<game_id>/index.json" },
  { "name": "books_base.jsonl.zst",   "url": "https://…/books_base.jsonl.zst" },
  { "name": "lookUpTable_base_0.csv", "url": "https://…/lookUpTable_base_0.csv" }
]
```
Show them in your box admin, or hand the three files to whoever uploads them to the Stake
**ACP dashboard** (that's what makes a game live — S3 is just storage).

---

## Prize odds — the one thing to get right

The service needs, across a box's prizes:
- **probabilities that sum to exactly `1.0`**, each a **multiple of `1/100000`**, and
- **RTP `< 1.0`**, where RTP = `Σ (payout ÷ box_cost, snapped to 0.1×) × prob`.

If your existing prizes store **weights** or **percentages** instead of normalized
probabilities, normalize in the mapping before sending:
```php
$total = $box->prizes->sum('weight');
'prob' => round($p->weight / $total, 5),   // 5 dp = a multiple of 1/100000
```
Rounding can make the sum land at `0.99999`/`1.00001` — nudge the largest prize by the
remainder if your source data is coarse, or keep prize probabilities to ≤5 decimals at the
source. If odds/economics are off, the API returns `400` with the exact reason — surface that
to the admin rather than swallowing it.

---

## Error handling

| Response | Meaning | Action |
|----------|---------|--------|
| `400 Invalid manifest / Assembled manifest invalid` | Bad odds/economics | Show the message to the admin; fix the prizes. |
| `401` | Wrong/missing API key | Fix `MATHSDK_KEY`. |
| `409` | prod `game_id` already built | Client passes `overwrite=true`; or change the box name. |
| job `deploy_status: "failed"` | Build OK, S3 upload failed | Rebuild (`overwrite=true`); check the service's S3 creds. |

## Notes

- **Same-box only:** `127.0.0.1` works because Laravel + the container share the host. Split
  them → call the build server's private IP / TLS subdomain instead.
- **`mode`:** `dev` = fast, non-publishable preview (no S3 upload); `prod` = real, uploaded build.
- **`game_id`** is derived from the box name; rebuilding overwrites its files. Pass an explicit
  `game_id` in `$spec` if you want to pin it (e.g. to your box's UUID).
