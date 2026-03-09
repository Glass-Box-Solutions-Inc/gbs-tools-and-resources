# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
#
# Multi-stage Alpine build for invoice-reconciliation-tester.
# Stage 1: Install production dependencies only.
# Stage 2: Install all dependencies, generate Prisma client, compile TypeScript.
# Stage 3: Lean runtime image with compiled JS + Prisma client.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* tsconfig.json ./
COPY prisma/ ./prisma/
RUN npm ci
RUN npx prisma generate
COPY src/ ./src/
RUN npx tsc

FROM node:20-alpine AS runtime
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=deps --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appgroup /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
COPY --from=builder --chown=appuser:appgroup /app/prisma ./prisma
COPY --from=builder --chown=appuser:appgroup /app/package.json ./package.json
COPY --from=builder --chown=appuser:appgroup /app/node_modules/prisma ./node_modules/prisma
COPY --from=builder --chown=appuser:appgroup /app/node_modules/.bin/prisma ./node_modules/.bin/prisma
USER appuser
ENV NODE_ENV=production
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:${PORT:-5520}/health || exit 1
CMD ["sh", "-c", "./node_modules/.bin/prisma migrate deploy && node dist/server.js"]
