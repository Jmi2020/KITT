# syntax=docker/dockerfile:1.6
FROM node:20-alpine AS base

WORKDIR /app

ENV NODE_ENV=production \
    CI=true

COPY services/ui/package*.json ./services/ui/

RUN if [ -f services/ui/package.json ]; then cd services/ui && npm install --production && cd /app; else echo "package.json not present yet" ; fi

COPY services/ui ./services/ui

RUN if [ -f services/ui/package.json ]; then cd services/ui && npm run build || echo "Build skipped (no scripts defined yet)"; fi

EXPOSE 4173
CMD ["sh", "-c", "cd services/ui && npm run start || npm run dev"]
