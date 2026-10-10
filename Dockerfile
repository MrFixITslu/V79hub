ARG NODE_BASE=node:22-alpine
FROM ${NODE_BASE}

WORKDIR /app
RUN apk add --no-cache python3 make g++
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

ENV NODE_ENV=production
ENV PORT=3040
EXPOSE 3040

CMD ["./node_modules/.bin/tsx", "server.ts"]
