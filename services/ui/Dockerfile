# syntax=docker/dockerfile:1.6
FROM node:20-alpine AS build

WORKDIR /app

ENV PNPM_HOME=/root/.local/share/pnpm \
    PATH="/root/.local/share/pnpm:$PATH"

RUN corepack enable

ARG VITE_API_BASE=http://localhost:8080
ARG VITE_MQTT_URL=ws://localhost:9001

ENV VITE_API_BASE=${VITE_API_BASE} \
    VITE_MQTT_URL=${VITE_MQTT_URL} \
    NODE_ENV=production

COPY services/ui/pnpm-lock.yaml services/ui/package.json ./
RUN pnpm install --frozen-lockfile

COPY services/ui/ ./
RUN pnpm build

FROM nginx:1.27-alpine AS runtime

COPY services/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 4173
CMD ["nginx", "-g", "daemon off;"]
