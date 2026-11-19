ARG NODE_BASE=node:22-alpine
ARG RUNTIME_BASE=alpine:3.24
FROM ${NODE_BASE} AS node-runtime
FROM node-runtime AS builder
WORKDIR /app
RUN apk add --no-cache python3 make g++
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build && npm prune --omit=dev --no-audit --no-fund

# Ship the Node executable and production app, not npm/build/test toolchains.
FROM ${RUNTIME_BASE} AS production
RUN apk add --no-cache libstdc++ python3 && addgroup -g 1000 node && adduser -u 1000 -G node -s /bin/sh -D node
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
WORKDIR /app
COPY --from=builder /app /app
ENV NODE_ENV=production
ENV PORT=3040
EXPOSE 3040
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["./node_modules/.bin/tsx", "server.ts"]
