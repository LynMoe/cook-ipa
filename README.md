# cook-ipa

iOS Ad Hoc OTA (Over-The-Air) distribution service. Upload an `.ipa` → auto re-sign with your certificate → publish an `itms-services://` install link.

## How it works

1. Upload an `.ipa` via the web UI or API
2. The server parses bundle ID, version, and app icon from the IPA
3. A matching Ad Hoc Provisioning Profile is fetched (or created) via Apple App Store Connect API
4. [`zsign`](https://github.com/zhlynn/zsign) re-signs the IPA with your P12 certificate and the provisioning profile
5. The signed IPA, `manifest.plist`, and app icon are uploaded to S3-compatible object storage (Tencent Cloud COS)
6. A scannable QR code and `itms-services://` install link are returned for iOS devices

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + Flask 3 |
| Frontend | React 19 + Vite + Tailwind CSS |
| Signing | `zsign` (pre-compiled binary in `bin/`) |
| Storage | S3-compatible (Tencent Cloud COS / AWS S3) |
| Apple API | App Store Connect API (JWT) |
| Deployment | Docker + docker-compose |

## Prerequisites

- Docker & docker-compose
- An Apple Developer account with:
  - An **App Store Connect API key** (`.p8` file, Key ID, Issuer ID)
  - A **Distribution certificate** exported as `.p12` with password
- An S3-compatible bucket (Tencent Cloud COS, AWS S3, etc.) with public read access on objects
- A publicly reachable HTTPS domain pointing to your bucket (iOS requires HTTPS for OTA installs)

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/cook-ipa.git
cd cook-ipa
```

### 2. Prepare certificates

```
certs/
├── AuthKey.p8        # App Store Connect API private key
└── cert.p12          # Distribution certificate (P12)
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

See [Configuration](#configuration) for a full description of each variable.

### 4. Run with Docker

```bash
docker-compose up -d
```

The web UI is available at `http://localhost:5005`.

> **Tip:** Run `docker-compose logs -f` to monitor the signing pipeline in real time.

## Configuration

Copy `.env.example` to `.env` and fill in the values below.

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Flask session secret — use a long random string |
| `FLASK_DEBUG` | | `true` / `false` (default `false`) |
| `APPLE_KEY_ID` | ✅ | App Store Connect API Key ID (e.g. `ABC123DEFG`) |
| `APPLE_ISSUER_ID` | ✅ | App Store Connect Issuer UUID |
| `APPLE_PRIVATE_KEY_PATH` | ✅ | Path to the `.p8` key file inside the container (`/app/certs/AuthKey.p8`) |
| `P12_PATH` | ✅ | Path to the `.p12` certificate inside the container (`/app/certs/cert.p12`) |
| `P12_PASSWORD` | ✅ | Password for the P12 file |
| `S3_ACCESS_KEY` | ✅ | S3 / COS access key ID |
| `S3_SECRET_KEY` | ✅ | S3 / COS secret access key |
| `S3_ENDPOINT` | ✅ | S3 endpoint URL (e.g. `https://cos.ap-shanghai.myqcloud.com`) |
| `S3_REGION` | ✅ | S3 region (e.g. `ap-shanghai`) |
| `S3_BUCKET` | ✅ | Bucket name |
| `S3_PREFIX` | | Object key prefix / folder (default `ota`) |
| `S3_EXTERNAL_DOMAIN` | ✅ | Public HTTPS base URL for assets (e.g. `https://assets.example.com`). **Must be HTTPS** — iOS OTA requires it. |
| `HOST` | | Bind address (default `0.0.0.0`) |
| `PORT` | | Listen port (default `5005`) |

## Project layout

```
cook-ipa/
├── app/
│   ├── domain/          # Core logic: provisioning profile resolver
│   ├── routes/          # Flask blueprints (upload, builds, devices, profiles)
│   └── services/        # Apple API client, IPA analyzer, signer, S3 storage
├── frontend/            # React SPA (Vite, built into app/static/spa/)
├── bin/
│   └── zsign            # Pre-compiled zsign binary
├── certs/               # Runtime certificates (not committed)
├── builds/              # Build artefacts & logs (not committed)
├── config.py
├── run.py
├── Dockerfile
└── docker-compose.yml
```

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload an `.ipa` file (multipart/form-data, field `file`) |
| `POST` | `/api/upload-url` | Trigger signing from a remote IPA URL |
| `GET` | `/api/builds` | List all builds |
| `GET` | `/api/builds/<id>` | Get build details & install link |
| `GET` | `/api/builds/<id>/log` | Streaming build log |
| `GET` | `/api/devices` | List registered test devices |
| `POST` | `/api/devices` | Register a new device (UDID + name) |
| `GET` | `/api/profiles` | List provisioning profiles |

## Development

### Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
python run.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # Vite dev server proxies /api to http://localhost:5005
```

### Build frontend for production

```bash
cd frontend && npm run build
# Output goes to app/static/spa/
```

## License

MIT
