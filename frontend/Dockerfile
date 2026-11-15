# syntax=docker/dockerfile:1.7
# Build context: repository root (needs ./frontend and ./nginx).

# ---- build the SPA -------------------------------------------------------------
FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_APP_NAME="Asset Management Tools"
ENV VITE_APP_NAME=${VITE_APP_NAME}
RUN npm run build

# ---- nginx edge (Alpine nginx + Brotli module): static SPA + reverse proxy -----
FROM alpine:3.20 AS runtime
RUN apk add --no-cache nginx nginx-mod-http-brotli \
    && rm -f /etc/nginx/http.d/default.conf \
    && mkdir -p /etc/nginx/admin-auth /etc/nginx/conf.d /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/snippets /etc/nginx/snippets
COPY nginx/conf.d /etc/nginx/conf.d
COPY --from=build /app/dist /usr/share/nginx/html
# Validate the config at build time (the "api" upstream only resolves inside the compose network,
# so the check uses a copy pointing at localhost).
RUN chown -R nginx:nginx /usr/share/nginx/html /var/lib/nginx /var/log/nginx \
    && sed 's/server api:2000/server 127.0.0.1:2000/' /etc/nginx/nginx.conf > /tmp/nginx-check.conf \
    && nginx -t -e /dev/stderr -c /tmp/nginx-check.conf \
    && rm -f /tmp/nginx-check.conf /tmp/nginx.pid
USER nginx
EXPOSE 2025
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:2025/nginx-health || wget --no-check-certificate -qO- https://127.0.0.1:2025/nginx-health || exit 1
CMD ["nginx", "-e", "/dev/stderr", "-g", "daemon off;"]
