# Squeegee — Cloud Run container
# Two-stage Alpine build: deps stage keeps node_modules out of final layer context.
# git is required because pipeline stages run `git log` and `git diff` on cloned repos.

FROM node:20-alpine AS deps
WORKDIR /app
RUN apk upgrade --no-cache
COPY package.json .
RUN npm install --production

FROM node:20-alpine AS runtime
WORKDIR /app

# git is required by pipeline stages (git log, git diff, git status)
# Upgrade all system packages (patch OS-level CVEs), install git, remove npm from runtime
RUN apk upgrade --no-cache && \
    apk add --no-cache git && \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

COPY --from=deps /app/node_modules ./node_modules
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY intelligence/ ./intelligence/
COPY config/ ./config/
COPY squeegee.config.json .
COPY package.json .

ENV PORT=8080
EXPOSE 8080

# Run as non-root for security
USER node

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://localhost:8080/health').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))"

CMD ["node", "--expose-gc", "src/server.js"]
