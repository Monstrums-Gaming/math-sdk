# Backoffice integration guide (Laravel)

How to call the mystery-box build service from your Laravel backoffice: an admin defines a
box → your app asks the service to build it → the service uploads the publish files to S3 →
you store the returned URLs against the box.

The service runs as a container on the **same server** as your Forge app, bound to
`127.0.0.1:8000`, so Laravel calls it over loopback with an API key. No public exposure.

Full API reference: [`API.md`](API.md). This guide is the Laravel side.

---

## The flow

```
Admin fills a box form  ─▶  POST /manifests?build=true&mode=prod   (returns job_id)
                        ─▶  poll GET /builds/{job_id}  until  status = succeeded
                        ─▶  save s3_files[].url on the box record
```

- **Build is async** — a prod build takes seconds to a minute+. Kick it off, store the
  `job_id`, and **poll from a queued job**, never inside the web request.
- **Ephemeral mode** is on, so the service returns stable S3 URLs (`s3_files[].url`) and
  deletes its local copy. Your DB becomes the record of "box → files".

---

## 1. Configuration

`.env` (your Laravel app's env, Forge-managed):
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

## 2. A thin API client

`app/Services/MathSdk.php`:
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
            ->timeout(30);   // each call is quick; the *build* is what's slow (we poll)
    }

    /**
     * Assemble a manifest from simplified box fields and start a build.
     * Returns the decoded body incl. ['job' => ['job_id' => ...]].
     * Throws on 4xx/5xx (e.g. 400 = bad box economics/odds).
     */
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

## 3. Store the box + its build result

Migration (`php artisan make:migration create_mystery_boxes_table`):
```php
Schema::create('mystery_boxes', function (Blueprint $t) {
    $t->id();
    $t->string('name');
    $t->decimal('box_cost', 8, 2);
    $t->decimal('rtp', 6, 4)->nullable();          // returned by the service
    $t->json('prizes');                            // the admin's prize rows
    $t->string('game_id')->nullable();             // returned by the service
    $t->string('build_job_id')->nullable();
    $t->string('build_status')->default('draft');  // draft|building|succeeded|failed
    $t->text('build_error')->nullable();
    $t->json('s3_files')->nullable();              // [{name,key,uri,url}, ...]
    $t->timestamps();
});
```

---

## 4. Kick off the build (controller)

```php
use App\Jobs\BuildMysteryBox;
use App\Models\MysteryBox;

public function store(Request $request)
{
    $data = $request->validate([
        'name'      => 'required|string',
        'box_cost'  => 'required|numeric|min:0.01',
        'prizes'    => 'required|array|min:1',
        'prizes.*.name'   => 'required|string',
        'prizes.*.payout' => 'required|numeric|min:0',
        'prizes.*.prob'   => 'required|numeric|gt:0|lte:1',
    ]);

    $box = MysteryBox::create([
        'name'         => $data['name'],
        'box_cost'     => $data['box_cost'],
        'prizes'       => $data['prizes'],
        'build_status' => 'building',
    ]);

    BuildMysteryBox::dispatch($box->id);

    return response()->json(['id' => $box->id, 'status' => 'building']);
}
```

---

## 5. The build job (assemble → poll → save)

`app/Jobs/BuildMysteryBox.php`:
```php
<?php

namespace App\Jobs;

use App\Models\MysteryBox;
use App\Services\MathSdk;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;

class BuildMysteryBox implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 600;   // allow the poll loop to run

    public function __construct(public int $boxId) {}

    public function handle(MathSdk $sdk): void
    {
        $box = MysteryBox::findOrFail($this->boxId);

        // Build the simplified box spec the /manifests endpoint expects.
        $spec = [
            'game_name'       => $box->name,
            'provider_number' => 3,              // your ACP studio id
            'provider_name'   => 'monstrum',
            'box_cost'        => (float) $box->box_cost,
            'cost_model'      => 'unit',         // ACP-valid
            'prizes'          => $box->prizes,   // [{name,payout,prob}, ...]
        ];

        try {
            $res   = $sdk->assembleAndBuild($spec, mode: 'prod', overwrite: true);
            $jobId = $res['job']['job_id'];
            $box->update([
                'build_job_id' => $jobId,
                'game_id'      => $res['game_id'],
                'rtp'          => $res['rtp'],
            ]);
        } catch (\Throwable $e) {
            // 400 = bad odds/economics (RTP >= 1.0, probs != 1.0, etc.)
            $box->update(['build_status' => 'failed', 'build_error' => $e->getMessage()]);
            return;
        }

        // Poll until the build settles (prod builds: seconds to a minute+).
        for ($i = 0; $i < 60; $i++) {
            sleep(5);
            $status = $sdk->getBuild($jobId);

            if ($status['status'] === 'succeeded') {
                $box->update([
                    'build_status' => 'succeeded',
                    's3_files'     => $status['s3_files'],   // save the URLs
                ]);
                return;
            }
            if ($status['status'] === 'failed') {
                $box->update(['build_status' => 'failed', 'build_error' => $status['error'] ?? 'build failed']);
                return;
            }
        }

        $box->update(['build_status' => 'failed', 'build_error' => 'build timed out']);
    }
}
```

You need a running queue worker — Forge sets this up (site → **Queue**). The scheduler isn't
required; the job self-polls.

---

## 6. Using the result

After success, `$box->s3_files` holds the stable, savable paths:
```json
[
  { "name": "index.json",             "url": "https://juice-cdn.s3.ap-southeast-2.amazonaws.com/math-sdk/staging/<game_id>/index.json" },
  { "name": "books_base.jsonl.zst",   "url": "https://…/books_base.jsonl.zst" },
  { "name": "lookUpTable_base_0.csv", "url": "https://…/lookUpTable_base_0.csv" }
]
```
Show them in the admin UI, or hand the three files to whoever uploads to the Stake **ACP
dashboard** (that's what makes the game live — S3 is just your storage).

---

## Box economics — the one rule admins must respect

`cost_model: "unit"` RTP is `Σ (payout ÷ box_cost, snapped to 0.1×) × prob`, and it **must be
< 1.0** or the service returns `400 "prizes pay X RTP (>= 1.0)"`. Also every `prob` must be a
multiple of `1/100000` and they must sum to `1.0`. Surface these `400` messages to the admin
so they can fix the odds — don't swallow them. Aim RTP around 0.80–0.90.

---

## Error handling cheat-sheet

| Response | Meaning | What to do |
|----------|---------|-----------|
| `400 Invalid manifest / Assembled manifest invalid` | Bad odds/economics | Show the message to the admin; let them fix the box. |
| `401` | Wrong/missing API key | Fix `MATHSDK_KEY`. |
| `409` | prod `game_id` already built | Pass `overwrite=true` (the client does) or bump the game name. |
| job `deploy_status: "failed"` | Build OK but S3 upload failed | Retry the build (`overwrite=true`); check the service's S3 creds. |

---

## Notes

- **Same-box only:** `127.0.0.1` works because Laravel and the container share the host. If
  you split them, call the build server's private IP / TLS subdomain instead.
- **Idempotency:** `game_id` is derived from the box name (`<provider>_<slug>`); rebuilding
  the same box overwrites its files. Pass an explicit `game_id` in `$spec` if you want to
  control it.
- **dev vs prod:** use `mode=dev` for a fast, non-publishable preview (no S3 upload); `prod`
  for the real, uploaded build.
