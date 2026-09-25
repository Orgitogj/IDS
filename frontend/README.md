# IDS dashboard (Angular)

This is the analyst dashboard for the IDS. It shows detected alarms and incidents live,
explains individual detections, and gives admins control over users, models and severity
thresholds. The UI text is in Albanian. For the whole system, see the
[root README](../README.md).

## What it does

| Page | Purpose |
|---|---|
| Login | JWT sign-in against the backend. A refresh token is kept in an HTTP-only cookie. |
| Overview | Alarm, flow, model and experiment summaries, updated live. |
| Alarms | Live alarm list and grouped incidents. Opening an alarm shows the flow's top SHAP features and can request an LLM explanation. |
| Flows | Ingested network flows with their predictions. |
| Experiments | Recorded model evaluation results. |
| Models | Registered models; admins can activate one. |
| Topology | Diagram of the isolated lab network (Kali `192.168.50.10` → Metasploitable2 `192.168.50.20`). |
| Users, Settings | Admin only: manage accounts and alarm-severity thresholds. |

Standalone Angular 22 components with signals, Tailwind CSS 4, Chart.js through ng2-charts,
and STOMP over SockJS for live updates.

## What it expects to be running

The service addresses are hard-coded; there are no environment files. Each service file in
`src/app/core/services/` defines its own URL constant.

| Service | Address | Used for |
|---|---|---|
| Spring Boot backend | `http://localhost:8080/api/...` | Authentication and all data |
| Backend WebSocket | `http://localhost:8080/ws` (SockJS) | `/topic/alarms`, `/topic/incidents`, `/topic/models/active` |
| ml-service | `http://localhost:8000/api` | `/predict` (SHAP) and `/explain` (LLM) on the Alarms page |

Every request and the WebSocket connection carry the JWT issued by the backend.

- **Port.** The dev server must run on `http://localhost:4200`. That is the only origin the
  backend allows by default (`IDS_ALLOWED_ORIGINS`) and the only one ml-service allows.
- **Explanations.** SHAP and explanations work only when ml-service is up and shares the
  backend's `IDS_JWT_SECRET`. LLM explanations also need `ANTHROPIC_API_KEY` in ml-service.

## Run locally

Requires Node.js 24 and npm 11 (the versions verified here). Start the database, backend
and ml-service first (see the [root README](../README.md#5-running-locally)). Then:

```bash
npm ci
npm start                # ng serve → http://localhost:4200
```

Sign in as `admin` with the `IDS_ADMIN_PASSWORD` you gave the backend. The dashboard stays
empty until flows are ingested, for example with the CICIDS2017 replay script described in
the root README.

## Build and test

```bash
npm run build            # production build → dist/IDS-Frontend/
npm test                 # Vitest via ng test (watch mode; add -- --watch=false for one run)
```

`app.spec.ts` covers the routing. The root renders only a router outlet. Unauthenticated
visitors are sent to `/login`, authenticated users land on `/overview`, and admin-only pages
redirect non-admins to `/overview`.
