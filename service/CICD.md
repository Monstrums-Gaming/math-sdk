# CI/CD with Amazon ECR + manual EC2 setup (runbook)

Automate: **push to GitHub → build image → push to ECR → deploy on the EC2 box**, using
GitHub Actions with **OIDC** (no long-lived AWS keys) and **SSM** to deploy (no SSH keys, no
open ports). Targets the same EC2 instance that runs the Forge backoffice + the service
container.

```
git push (staging) ─▶ GitHub Actions ─▶ build arm64 ─▶ push to ECR ─▶ SSM RunShellScript ─▶ docker pull + restart on EC2 ─▶ curl /healthz
```

The ready-to-run workflow is **`.github/workflows/deploy-service.yml`** (triggers on push to
`staging` + manual dispatch). This doc is the one-time setup behind it — **Part A** (AWS/GitHub
for CI) and **Part B** (the EC2 box). Both were needed to make deploys hands-off.

> **Architecture note:** the target box `dev.theboxforge.com` is a **`t4g.medium` (AWS Graviton
> = arm64)**. The image **must be arm64** — an amd64 image fails on the box with
> `exec format error`. The workflow cross-builds arm64 via QEMU + buildx (GitHub runners are
> amd64). If your box is x86_64, switch `--platform linux/arm64` → `linux/amd64`.

## Concrete values (this deployment)

| Setting | Value |
|---------|-------|
| Account | `493499579237` |
| Region (ECR, EC2, SSM) | `us-east-1` |
| GitHub repo | `Monstrums-Gaming/math-sdk` |
| Branch | `staging` |
| ECR repo | `mysterybox-build-service-staging` |
| Image arch | `linux/arm64` (Graviton t4g) |
| OIDC deploy role | `arn:aws:iam::493499579237:role/gha-deploy` |
| EC2 instance | `i-0dd60212d9ea2c1af` (set as GitHub **variable** `EC2_INSTANCE_ID`) |
| EC2 instance role | `theboxforge-role` (+ profile `theboxforge-profile`) |
| `.env` on the box | `/home/ubuntu/math-sdk/.env` |
| Container name | `mbs`, bound to `127.0.0.1:8000` |

Run all `aws` setup commands from a machine with **admin** credentials (e.g. your Mac). Run
`docker`/`curl` commands **on the box**.

---

# Part A — GitHub Actions → ECR (one-time)

## A1. Create the ECR repository

```sh
aws ecr create-repository \
  --repository-name mysterybox-build-service-staging \
  --image-scanning-configuration scanOnPush=true \
  --region us-east-1
```
(Optional) keep only the last 10 images:
```sh
aws ecr put-lifecycle-policy --repository-name mysterybox-build-service-staging --region us-east-1 \
  --lifecycle-policy-text '{"rules":[{"rulePriority":1,"description":"keep last 10",
    "selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10},
    "action":{"type":"expire"}}]}'
```

## A2. Register GitHub as an OIDC provider (once per account)

```sh
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```
(`EntityAlreadyExists` = fine.)

## A3. Create the `gha-deploy` role GitHub assumes

```sh
cat > /tmp/trust.json <<'JSON'
{ "Version":"2012-10-17","Statement":[{
  "Effect":"Allow",
  "Principal":{"Federated":"arn:aws:iam::493499579237:oidc-provider/token.actions.githubusercontent.com"},
  "Action":"sts:AssumeRoleWithWebIdentity",
  "Condition":{
    "StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com"},
    "StringLike":{"token.actions.githubusercontent.com:sub":"repo:Monstrums-Gaming/math-sdk:*"}
  }}]}
JSON

cat > /tmp/gha-deploy-policy.json <<'JSON'
{ "Version":"2012-10-17","Statement":[
  {"Sid":"EcrAuth","Effect":"Allow","Action":"ecr:GetAuthorizationToken","Resource":"*"},
  {"Sid":"EcrPush","Effect":"Allow",
   "Action":["ecr:BatchCheckLayerAvailability","ecr:InitiateLayerUpload","ecr:UploadLayerPart",
             "ecr:CompleteLayerUpload","ecr:PutImage","ecr:BatchGetImage"],
   "Resource":"arn:aws:ecr:us-east-1:493499579237:repository/mysterybox-build-service-staging"},
  {"Sid":"SsmDeploy","Effect":"Allow",
   "Action":["ssm:SendCommand","ssm:GetCommandInvocation"],"Resource":"*"}
]}
JSON

aws iam create-role --role-name gha-deploy --assume-role-policy-document file:///tmp/trust.json
aws iam put-role-policy --role-name gha-deploy --policy-name gha-deploy --policy-document file:///tmp/gha-deploy-policy.json
```
The trust `sub` uses `:*` (any branch) so `staging` + `workflow_dispatch` both work. Tighten
to `repo:Monstrums-Gaming/math-sdk:ref:refs/heads/staging` if you want to lock it down.

## A4. Set the GitHub repo variable

The workflow's deploy step is gated on `vars.EC2_INSTANCE_ID` (skips if unset — so CI still
builds+pushes before the box is ready).
```sh
gh variable set EC2_INSTANCE_ID --body "i-0dd60212d9ea2c1af" --repo Monstrums-Gaming/math-sdk
```
(or repo → Settings → Secrets and variables → Actions → **Variables**).

---

# Part B — The EC2 box (one-time)

## B1. Instance role: ECR pull + SSM

The box needs an IAM instance role with **ECR read** (to pull) and **SSM core** (to receive
deploy commands). Forge boxes ship with **no** instance role — create and attach one:

```sh
cat > /tmp/ec2-trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
aws iam create-role --role-name theboxforge-role --assume-role-policy-document file:///tmp/ec2-trust.json
aws iam attach-role-policy --role-name theboxforge-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name theboxforge-role --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam create-instance-profile --instance-profile-name theboxforge-profile
aws iam add-role-to-instance-profile --instance-profile-name theboxforge-profile --role-name theboxforge-role
aws ec2 associate-iam-instance-profile --instance-id i-0dd60212d9ea2c1af \
  --iam-instance-profile Name=theboxforge-profile --region us-east-1
```
Verify (from the admin machine — the instance role itself can't query SSM inventory):
```sh
aws ec2 describe-iam-instance-profile-associations --region us-east-1 \
  --filters "Name=instance-id,Values=i-0dd60212d9ea2c1af" --query 'IamInstanceProfileAssociations[].State' --output text
# → associated
```

## B2. Register the SSM agent

The agent must be running to register with the new role (restart so it picks up creds):
```sh
# on the box
sudo snap install amazon-ssm-agent --classic 2>/dev/null || true
sudo snap restart amazon-ssm-agent 2>/dev/null || sudo systemctl restart amazon-ssm-agent
```
Verify **from the admin machine** (not the box):
```sh
aws ssm describe-instance-information --region us-east-1 \
  --query "InstanceInformationList[].InstanceId" --output text        # → i-0dd60212d9ea2c1af
```

## B3. Install Docker

```sh
# on the box
sudo apt-get update && sudo apt-get install -y docker.io
sudo usermod -aG docker ubuntu
newgrp docker
docker --version
```

## B4. Create the `.env`

You don't need the repo on the box — the image has the code; you only need config.
```sh
# on the box
mkdir -p /home/ubuntu/math-sdk
nano /home/ubuntu/math-sdk/.env
```
```
API_KEY=<a long random secret; also set as Laravel's MATHSDK_KEY>
AWS_S3_BUCKET=juice-cdn
S3_PREFIX=math-sdk/staging
AWS_REGION=ap-southeast-2
AWS_ACCESS_KEY_ID=<key with s3:PutObject on the bucket>
AWS_SECRET_ACCESS_KEY=<secret>
```
> ⚠️ **No inline comments on value lines** — Docker `--env-file` keeps them as part of the
> value (breaks the bucket name/region silently). Comments go on their own `#` lines.
> The `.env` AWS keys are for the **container's S3 upload** — they are separate from how the
> box pulls from ECR (that's the instance role, below).

## B5. Remove any static AWS creds from the box (so ECR uses the instance role)

If you ever ran `aws configure` on the box, its static keys **shadow** the instance role — and
if those keys lack ECR (e.g. an S3-only user), `aws ecr get-login-password` fails with
`AccessDenied ... ecr:GetAuthorizationToken`. Remove them so the role is used:
```sh
# on the box
rm -rf ~/.aws
aws sts get-caller-identity --region us-east-1
# Arn should be  arn:aws:sts::493499579237:assumed-role/theboxforge-role/i-0dd6...
```

## B6. Manual first deploy (also the fallback)

```sh
# on the box
REG=493499579237.dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $REG
docker rm -f mbs 2>/dev/null || true
docker pull $REG/mysterybox-build-service-staging:latest
docker run -d --name mbs --restart unless-stopped -p 127.0.0.1:8000:8000 \
  --cpus 2 --memory 2g --env-file /home/ubuntu/math-sdk/.env \
  $REG/mysterybox-build-service-staging:latest
docker ps --filter name=mbs
curl http://127.0.0.1:8000/healthz          # {"status":"ok"}
```
Do this once to prove the box works before relying on auto-deploy.

---

# Part C — The workflow

`.github/workflows/deploy-service.yml` (already committed; shown here for reference):

```yaml
name: deploy-build-service
on:
  push:
    branches: [staging]
    paths: ['service/**','games/mystery_box_dynamic/**','src/**','requirements.txt','setup.py','.github/workflows/deploy-service.yml']
  workflow_dispatch: {}

permissions:
  id-token: write        # OIDC
  contents: read

env:
  AWS_REGION: us-east-1
  ACCOUNT_ID: "493499579237"
  ECR_REPO: mysterybox-build-service-staging
  ENV_FILE: /home/ubuntu/math-sdk/.env

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::493499579237:role/gha-deploy
          aws-region: ${{ env.AWS_REGION }}
      - id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      # arm64 (Graviton t4g); GitHub runners are amd64, so cross-build with QEMU + buildx.
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - name: Build & push image (arm64)
        run: |
          IMG="${{ steps.ecr.outputs.registry }}/${ECR_REPO}:${GITHUB_SHA::12}"
          LATEST="${{ steps.ecr.outputs.registry }}/${ECR_REPO}:latest"
          docker buildx build --platform linux/arm64 -f service/Dockerfile -t "$IMG" -t "$LATEST" --push .
          echo "IMG=$IMG" >> "$GITHUB_ENV"

      - name: Deploy on EC2 via SSM
        if: ${{ vars.EC2_INSTANCE_ID != '' }}
        run: |
          REG="${{ steps.ecr.outputs.registry }}"
          CMD_ID=$(aws ssm send-command \
            --instance-ids "${{ vars.EC2_INSTANCE_ID }}" \
            --document-name AWS-RunShellScript \
            --parameters commands="[
              \"aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REG\",
              \"docker pull $IMG\",
              \"docker rm -f mbs || true\",
              \"docker run -d --name mbs --restart unless-stopped -p 127.0.0.1:8000:8000 --cpus 2 --memory 2g --env-file $ENV_FILE $IMG\",
              \"sleep 3 && curl -sf http://127.0.0.1:8000/healthz\"
            ]" --query 'Command.CommandId' --output text)
          aws ssm wait command-executed --command-id "$CMD_ID" --instance-id "${{ vars.EC2_INSTANCE_ID }}" || true
          aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "${{ vars.EC2_INSTANCE_ID }}" \
            --query '{status:Status, out:StandardOutputContent, err:StandardErrorContent}' --output json
          STATUS=$(aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "${{ vars.EC2_INSTANCE_ID }}" --query Status --output text)
          test "$STATUS" = "Success"
```

Key facts:
- **`AWS-RunShellScript`** is the correct SSM document (not `AWS-RunShellCommand` → `InvalidDocument`).
- SSM runs the commands **as root**, so `ENV_FILE` is an absolute path root can read.
- ECR pull on the box uses the **instance role** (no keys in the SSM command).
- The final `curl /healthz` makes the job fail if the container doesn't come up.

---

# Part D — Run & verify

```sh
git push origin staging            # or: gh workflow run deploy-service.yml --ref staging
gh run watch "$(gh run list --workflow=deploy-service.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```
Expected deploy-step output ends with `"status": "Success"` and `{"status":"ok"}`.
Confirm on the box: `docker ps` shows `mbs` on the new SHA tag.

## Manual ECR push (bootstrap / no CI)

Build **arm64** locally (needs buildx) and push:
```sh
REG=493499579237.dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $REG
docker buildx build --platform linux/arm64 -f service/Dockerfile -t $REG/mysterybox-build-service-staging:manual --push .
```

## Rollback (deploy a prior SHA)

```sh
aws ssm send-command --instance-ids i-0dd60212d9ea2c1af --document-name AWS-RunShellScript --region us-east-1 \
  --parameters commands='["docker pull 493499579237.dkr.ecr.us-east-1.amazonaws.com/mysterybox-build-service-staging:<OLD_SHA>",
    "docker rm -f mbs || true",
    "docker run -d --name mbs --restart unless-stopped -p 127.0.0.1:8000:8000 --cpus 2 --memory 2g --env-file /home/ubuntu/math-sdk/.env 493499579237.dkr.ecr.us-east-1.amazonaws.com/mysterybox-build-service-staging:<OLD_SHA>"]'
```

---

## Troubleshooting (real issues hit setting this up)

| Symptom | Cause & fix |
|---------|-------------|
| Deploy step: `InvalidDocument` on SendCommand | Wrong SSM document name — use **`AWS-RunShellScript`**. |
| Container exits, `docker logs` shows **`exec format error`** | Arch mismatch — the box is arm64 (t4g). Build `--platform linux/arm64`. |
| `AccessDenied ... ecr:GetAuthorizationToken` on the box | A static `aws configure` cred (e.g. S3-only user) is shadowing the instance role. `rm -rf ~/.aws` on the box so the role is used. |
| `Not authorized ... sts:AssumeRoleWithWebIdentity` | Trust `sub` doesn't match — use `repo:Monstrums-Gaming/math-sdk:*` (or the exact branch ref). |
| `InvalidInstanceId` / SSM step can't reach box | Instance not registered — no instance role, or agent not running. Attach the role (B1), restart the agent (B2), confirm `describe-instance-information` (from admin machine). |
| `Unable to locate credentials` running `aws` on the box | You ran it before the instance role was attached, or `~/.aws` is empty and the role isn't associated yet. |
| `describe-instance-information` AccessDenied **on the box** | Run it from the admin machine — the instance role deliberately can't query SSM inventory. |
| Deploy step **skipped** | `EC2_INSTANCE_ID` repo variable not set (A4). |
| S3 upload fails in the container (`bucket = 'juice-cdn  # ...'`) | Inline comment in `.env` — Docker `--env-file` keeps it. Move comments to their own lines. |
| Container starts but S3 `AccessDenied` | The `.env` AWS keys lack `s3:PutObject` (this is separate from the ECR instance role). |

---

## AWS-native alternative

To keep everything inside AWS (no GitHub Actions): **CodePipeline** (GitHub via CodeStar
connection) → **CodeBuild** (`docker buildx` arm64 + push to ECR) → deploy via an SSM
RunCommand action. Same ECR + SSM mechanics, more IAM/setup. Prefer GitHub Actions unless
you're standardizing on AWS-native tooling.
