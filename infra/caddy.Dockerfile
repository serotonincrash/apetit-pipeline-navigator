# Caddy with the compiled web app baked in, so one container serves the app and proxies /api.
FROM node:24-alpine AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY docs/openapi.json /app/docs/openapi.json
COPY frontend/ ./
RUN npm run build

FROM caddy:2.10-alpine
COPY infra/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/frontend/dist /srv
