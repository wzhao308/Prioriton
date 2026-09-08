# Stage 1: build the static frontend. VITE_API_BASE is baked into the JS
# bundle at build time (Vite env handling - see src/api/client.ts), which is
# why it has to be a build ARG, not a plain container-runtime env var.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# Stage 2: Caddy serves those static files and reverse-proxies to the
# backend/noVNC - see ./Caddyfile. Caddy also handles TLS automatically
# (Let's Encrypt) given real DNS + reachable :80/:443, so there's no
# separate certbot step anywhere in this deploy.
FROM caddy:2-alpine
COPY --from=build /app/dist /srv/app
COPY Caddyfile /etc/caddy/Caddyfile
