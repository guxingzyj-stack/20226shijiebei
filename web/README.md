# P2-B Web

React + TypeScript + Vite + Tailwind frontend for the World Cup Jingcai
simulation game.

This web app is a virtual balance simulation game only. It does not provide
real lottery purchase, real betting, or proxy purchase features.

## Environment

```bash
VITE_API_BASE_URL=https://fifa2026.zeabur.app
```

Do not commit tokens, passwords, or secrets.

## Local Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run typecheck
npm run build
```

## Deployment

Zeabur service name: `web`

Use `web/Dockerfile` and set:

```bash
VITE_API_BASE_URL=https://fifa2026.zeabur.app
```

The API service must set `CORS_ORIGINS` to include the deployed web origin and
`http://localhost:5173` for local development. Avoid `*` when credentials are
used.
