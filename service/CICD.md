# CI/CD with Amazon ECR (step by step)

Automate: **push to GitHub → build image → push to ECR → deploy on the EC2 box**, using
GitHub Actions with **OIDC** (no long-lived AWS keys) and **SSM** to deploy (no SSH keys,
no open ports). Targets the same EC2 instance that runs the Forge backoffice + the service
container.

```
git push ──▶ GitHub Actions ──▶ build ──▶ push to ECR ──▶ SSM RunCommand ──▶ docker pull + restart on EC2
```

Fill in the placeholders once:

| Placeholder | Example |
|-------------|---------|
| `<ACCOUNT_ID>` | `123456789012` |
| `<REGION>` | `ap-southeast-2` |
| `<REPO>` (GitHub) | `Monstrums-Gaming/math-sdk` |
| `<INSTANCE_ID>` | `i-0abc123...` |
| `<ECR_REPO>` | `mysterybox-build-service` |

Prereqs: AWS CLI configured locally (admin, for the one-time setup), the EC2 box already
running the container per `DEPLOY.md`.

---

## Step 1 — Create the ECR repository

```sh
aws ecr create-repository \
  --repository-name mysterybox-build-service \
  --image-scanning-configuration scanOnPush=true \
  --region <REGION>
```

Registry URL is `​<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com`; the image will be
`<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/mysterybox-build-service:<tag>`.

(Optional) keep only recent images with a lifecycle policy:

```sh
aws ecr put-lifecycle-policy --repository-name mysterybox-build-service --region <REGION> \
  --lifecycle-policy-text '{"rules":[{"rulePriority":1,"description":"keep last 10",
    "selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10},
    "action":{"type":"expire"}}]}'
```

---

## Step 2 — Register GitHub as an OIDC identity provider (once per account)

Lets GitHub Actions assume an AWS role without stored keys.

```sh
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

(If it already exists you'll get `EntityAlreadyExists` — fine. AWS no longer validates the
thumbprint for GitHub, but the CLI still requires the flag.)

---

## Step 3 — Create the deploy role assumed by GitHub Actions

**Trust policy** — `trust.json` (scopes to your repo + `main` branch):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike":   { "token.actions.githubusercontent.com:sub": "repo:Monstrums-Gaming/math-sdk:ref:refs/heads/main" }
    }
  }]
}
```

**Permissions policy** — `gha-deploy-policy.json` (push to ECR + trigger the SSM deploy):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "EcrAuth",   "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
    { "Sid": "EcrPush",   "Effect": "Allow",
      "Action": ["ecr:BatchCheckLayerAvailability","ecr:InitiateLayerUpload","ecr:UploadLayerPart",
                 "ecr:CompleteLayerUpload","ecr:PutImage","ecr:BatchGetImage"],
      "Resource": "arn:aws:ecr:<REGION>:<ACCOUNT_ID>:repository/mysterybox-build-service" },
    { "Sid": "SsmDeploy", "Effect": "Allow",
      "Action": ["ssm:SendCommand","ssm:GetCommandInvocation","ssm:ListCommandInvocations"],
      "Resource": ["arn:aws:ec2:<REGION>:<ACCOUNT_ID>:instance/<INSTANCE_ID>",
                   "arn:aws:ssm:<REGION>::document/AWS-RunShellCommand",
                   "arn:aws:ssm:<REGION>:<ACCOUNT_ID>:*"] }
  ]
}
```

Create the role:

```sh
aws iam create-role --role-name gha-deploy \
  --assume-role-policy-document file://trust.json
aws iam put-role-policy --role-name gha-deploy \
  --policy-name gha-deploy --policy-document file://gha-deploy-policy.json
```

Role ARN: `arn:aws:iam::<ACCOUNT_ID>:role/gha-deploy`.

---

## Step 4 — Let the EC2 box pull from ECR and receive SSM commands

The **instance role** attached to the EC2 box needs:

```sh
# find the instance profile / role, then attach the two managed policies:
aws iam attach-role-policy --role-name <INSTANCE_ROLE> \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam attach-role-policy --role-name <INSTANCE_ROLE> \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
```

- The **SSM agent** is pre-installed on Ubuntu AWS AMIs. Confirm the box shows up:
  `aws ssm describe-instance-information --region <REGION>` should list `<INSTANCE_ID>`.
- Forge-provisioned boxes usually have **no** instance role — create one, attach the two
  policies above, and associate it with the instance.
- If the container uses this instance role for S3 too, remember the **IMDSv2 hop-limit = 2**
  fix (see `DEPLOY.md`).

---

## Step 5 — Add the GitHub Actions workflow

Create `.github/workflows/deploy-service.yml`:

```yaml
name: deploy-build-service
on:
  push:
    branches: [main]
    paths:
      - 'service/**'
      - 'games/mystery_box_dynamic/**'
      - 'src/**'
      - 'requirements.txt'
      - 'service/Dockerfile'
  workflow_dispatch: {}          # allow manual runs

permissions:
  id-token: write                # required for OIDC
  contents: read

env:
  AWS_REGION: <REGION>
  ECR_REPO: mysterybox-build-service
  INSTANCE_ID: <INSTANCE_ID>

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Assume AWS role (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/gha-deploy
          aws-region: ${{ env.AWS_REGION }}

      - name: Log in to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build & push image
        run: |
          IMG="${{ steps.ecr.outputs.registry }}/${ECR_REPO}:${GITHUB_SHA::12}"
          docker build -f service/Dockerfile -t "$IMG" .
          docker push "$IMG"
          echo "IMG=$IMG" >> "$GITHUB_ENV"
          echo "REG=${{ steps.ecr.outputs.registry }}" >> "$GITHUB_ENV"

      - name: Deploy on EC2 via SSM
        run: |
          CMD_ID=$(aws ssm send-command \
            --instance-ids "$INSTANCE_ID" \
            --document-name AWS-RunShellCommand \
            --comment "deploy $IMG" \
            --parameters commands="[
              \"aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REG\",
              \"docker pull $IMG\",
              \"docker rm -f mbs || true\",
              \"docker run -d --name mbs --restart unless-stopped -p 127.0.0.1:8000:8000 --cpus 2 --memory 2g --env-file /home/forge/math-sdk/.env $IMG\",
              \"sleep 3 && curl -sf http://127.0.0.1:8000/healthz\"
            ]" \
            --query 'Command.CommandId' --output text)
          echo "SSM command: $CMD_ID"
          aws ssm wait command-executed --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" || true
          aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
            --query '{status:Status, out:StandardOutputContent, err:StandardErrorContent}' --output json
```

Notes:
- The image is tagged with the commit SHA (immutable, easy rollback). Add a `:latest` tag
  too if you like.
- The deploy step reuses the exact `docker run` from `DEPLOY.md` (loopback bind, resource
  caps, `--env-file` on the box). Secrets stay in the box's `/home/forge/math-sdk/.env` —
  never in CI.
- The final `curl /healthz` makes the job **fail** if the new container doesn't come up.

---

## Step 6 — First run & verify

```sh
git push origin main            # or trigger "Run workflow" (workflow_dispatch)
```

- Watch the run in the GitHub **Actions** tab.
- Confirm the image landed: `aws ecr list-images --repository-name mysterybox-build-service --region <REGION>`.
- On the box: `docker ps` shows `mbs` running the new SHA tag; `curl http://127.0.0.1:8000/healthz`.

---

## Manual ECR push (no CI — for the first image or testing)

```sh
aws ecr get-login-password --region <REGION> \
  | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
docker build -f service/Dockerfile -t <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/mysterybox-build-service:manual .
docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/mysterybox-build-service:manual
```

## Rollback

Deploy any prior tag (SHAs are immutable):

```sh
aws ssm send-command --instance-ids <INSTANCE_ID> --document-name AWS-RunShellCommand \
  --parameters commands='["docker pull <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/mysterybox-build-service:<OLD_SHA>",
    "docker rm -f mbs || true",
    "docker run -d --name mbs --restart unless-stopped -p 127.0.0.1:8000:8000 --cpus 2 --memory 2g --env-file /home/forge/math-sdk/.env <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/mysterybox-build-service:<OLD_SHA>"]' \
  --region <REGION>
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | Trust policy `sub` must match your repo/branch exactly (`repo:Monstrums-Gaming/math-sdk:ref:refs/heads/main`). |
| ECR `denied` on push | `gha-deploy` policy missing an ECR action, or wrong repo ARN/region. |
| `InvalidInstanceId` on SSM | Instance not registered — no SSM agent or no `AmazonSSMManagedInstanceCore` on the instance role; check `aws ssm describe-instance-information`. |
| Container starts but S3 fails | Instance role lacks `s3:PutObject`, or IMDSv2 hop limit is 1 (raise to 2 — see `DEPLOY.md`). |
| `pull access denied` on the box | Instance role missing `AmazonEC2ContainerRegistryReadOnly`. |

---

## AWS-native alternative

To keep everything inside AWS (no GitHub Actions): **CodePipeline** (source: GitHub/CodeStar
connection) → **CodeBuild** (`docker build` + push to ECR via a `buildspec.yml`) → deploy
step (CodeDeploy or an SSM RunCommand action). Same ECR + SSM mechanics, more IAM/setup.
Prefer GitHub Actions unless you're standardizing on AWS-native tooling.
```
