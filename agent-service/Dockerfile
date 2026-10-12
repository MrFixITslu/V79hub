FROM node:24-alpine

WORKDIR /app
COPY package*.json ./
# The committed lockfile is the dependency authority; do not resolve latest packages.
RUN npm ci --include=dev --no-audit --no-fund

COPY tsconfig.json ./
COPY src ./src
COPY tests ./tests

# Runtime user matches the owner-restricted 0600 secret's UID:GID in pilot staging.
# No write access to /app is required; /tmp is supplied as tmpfs for read-only runs.
ENV NODE_ENV=production
ENV HOME=/tmp
ENV npm_config_cache=/tmp/npm-cache
USER 1000:1000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3055/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

EXPOSE 3055
CMD ["npm", "start"]
