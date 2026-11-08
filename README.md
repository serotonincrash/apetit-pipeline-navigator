# Climate and nature navigator

A web app that checks Apetit's farm and energy data, proposes fixes for people to approve, and
models climate risk to the supply. The spec in `docs/spec.md` describes what it does, and
`AGENTS.md` holds the rules for working in this repo.

The repo has 4 parts:

| Folder | What it holds |
| --- | --- |
| `backend/` | FastAPI app, run worker, recipe steps and agents (Python 3.12, uv) |
| `frontend/` | React web app (Vite, TanStack, Tailwind) |
| `infra/` | Compose file, Dockerfiles, Caddyfile and `.env.example` |
| `config/` | Assumptions and the action catalogue the seed job loads |

The app also needs the challenge package (`APETIT_CLIMATE_NATURE_NAVIGATOR_2026`), which is not
in git.

## Run it on a laptop

You need Docker with Compose v2, uv, Node 24 and the unzipped challenge package.

1. Start the shared Postgres and SeaweedFS.

   ```sh
   cp infra/.env.example infra/.env
   docker compose -f infra/docker-compose.yml --profile dev up -d
   ```

2. Write `backend/.env`. The defaults in `infra/.env.example` match the dev services, so only
   these lines are needed.

   ```sh
   DATABASE_URL=postgresql+psycopg://navigator:navigator@localhost:5432/navigator
   S3_ENDPOINT=localhost:8333
   S3_ACCESS_KEY=navigator
   S3_SECRET_KEY=navigator-dev
   PACKAGE_DIR=/absolute/path/to/APETIT_CLIMATE_NATURE_NAVIGATOR_2026
   LLM_MODE=fake
   ```

   `LLM_MODE=fake` gives fixed agent answers with no key. Set `LLM_MODE=opencode` with
   `OPENCODE_API_KEY` and `OPENCODE_MODEL` to use the real agents.

3. Create the tables and load the package.

   ```sh
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run python -m navigator.seed
   S3_BUCKET=navigator-seed uv run python -m navigator.seed
   ```

   The second seed fills the shared `navigator-seed` bucket, which `scripts/worktree.sh` copies
   from. It is needed once per computer.

4. Start the API and the worker, each in its own terminal, from `backend/`.

   ```sh
   uv run uvicorn navigator.api.main:app --port 8100
   uv run python -m navigator.worker.main
   ```

5. Start the web app from `frontend/` and open http://localhost:5200.

   ```sh
   npm install
   npm run dev
   ```

   The Vite dev server sends `/api` to port 8100.

### Work in a worktree

Each task gets its own branch, worktree, database and bucket inside the shared services.

```sh
scripts/worktree.sh up <name> <slot>   # worktree in .worktrees/<name>, API on 8100+slot
scripts/worktree.sh down <name>        # drops its databases and buckets, removes the worktree
```

### Checks

From `backend/`:

```sh
uv run pytest -m golden   # golden numbers, needs PACKAGE_DIR set
uv run pytest -m api      # API tests, needs TEST_DATABASE_URL and the dev services
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

From `frontend/`, `npm run build` and `npm run lint`. Run `pre-commit run --all-files` before
each commit.

## Deploy to a VM

One Compose file runs the whole app on a single Linux VM. Caddy is the only service with public
ports. It gets the HTTPS certificate, asks for a shared login, serves the web app and sends
`/api` to the API.

| Service | Role |
| --- | --- |
| `caddy` | HTTPS, shared login, web app files, proxy to the API |
| `api` | FastAPI under uvicorn |
| `worker` | Takes runs off the queue and executes them |
| `seed` | Runs once at start: migrations, package upload, action catalogue |
| `postgres` | Platform tables, run queue and run events |
| `seaweedfs` | S3 storage for the package and the run outputs |

### Prepare the VM

Use Ubuntu or Debian with at least 2 GB of memory, since the web app is built on the VM. Docker
runs everything else, so Caddy, Node and Python are not installed on the host. Stop any web
server that already listens on port 80 or 443.

```sh
curl -fsSL https://get.docker.com | sh
apt-get update && apt-get install -y git rsync
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
```

Point the domain's A record at the VM. Caddy needs it, and ports 80 and 443, to get the
certificate.

### Copy the code and the package

On the VM, clone the repo.

```sh
git clone https://github.com/serotonincrash/apetit-pipeline-navigator.git ~/navigator
```

From the laptop, copy the package. Leave out its `.venv`, which is about 600 MB the app does not
use.

```sh
rsync -az --exclude .venv --exclude .DS_Store \
  APETIT_CLIMATE_NATURE_NAVIGATOR_2026/ root@VM_IP:navigator-package/
```

### Fill in the environment

On the VM, make 2 random passwords and the login hash.

```sh
openssl rand -hex 16
openssl rand -hex 16
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext 'the shared password'
```

Then copy the example file and edit it.

```sh
cd ~/navigator/infra && cp .env.example .env
```

| Variable | Value on the VM |
| --- | --- |
| `COMPOSE_PROFILES` | `app` |
| `LLM_MODE` | `opencode` |
| `OPENCODE_API_KEY`, `OPENCODE_MODEL` | The OpenCode Go key and model id |
| `POSTGRES_PASSWORD` | The first random value |
| `S3_ACCESS_KEY` | Keep `navigator` |
| `S3_SECRET_KEY` | The second random value |
| `PACKAGE_DIR` | Absolute path, such as `/root/navigator-package` |
| `DOMAIN` | The domain pointed at the VM |
| `BASIC_AUTH_USER` | The shared login name |
| `BASIC_AUTH_HASH` | The hash, in single quotes because it contains `$` |

Leave `DATABASE_URL` and `S3_ENDPOINT` as they are. The Compose file sets them for the
containers.

Set `POSTGRES_PASSWORD` before the first start. Postgres keeps the password from its first start,
so a later change locks the API out of the database.

### Start the app

```sh
cd ~/navigator/infra
docker compose up -d --build
docker compose ps -a
```

The first build takes a few minutes. When it ends, `seed` shows as exited with code 0 and the 5
other services as running. Check the certificate and the API.

```sh
docker compose logs caddy | grep -i certificate
curl -u 'login:password' https://your.domain/api/health
```

The health check answers `{"status":"ok"}`. Then open the domain in a browser and log in.

### Prepare the demo

```sh
cd ~/navigator && scripts/reset_demo.sh "A. Reviewer"
```

The script empties the tables and the bucket, then reseeds the package and the catalogue. It runs
each recipe, approves the checked fixes in the given name, and runs again. It ends with a
`demo ready` line for each recipe. Run it again after people have used the app to get back to
the same state.

### Update a running VM

```sh
cd ~/navigator && git pull
cd infra && docker compose up -d --build
```

The seed job runs the migrations again on each start. Data stays in the `postgres` and
`seaweedfs` volumes, so never run `docker compose down -v`.

### When something fails

| Symptom | Where to look |
| --- | --- |
| `seed` exited with an error | `docker compose logs seed` |
| No certificate | DNS for the domain, ports 80 and 443, `docker compose logs caddy` |
| Port is already allocated | Another web server on the host holds 80 or 443 |
| A run fails | `docker compose logs worker`, and the run's error in the app |
| Build stops on a small VM | Add swap, or use a VM with more memory |
