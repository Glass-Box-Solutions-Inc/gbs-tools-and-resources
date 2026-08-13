FROM node:22-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json tsconfig.executables.json ./
COPY src ./src
COPY jobs ./jobs
COPY smoke ./smoke
RUN npm run build:executables

FROM node:22-slim AS runtime

ENV NODE_ENV=production
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist-runtime ./dist-runtime
COPY migrations ./dist-runtime/migrations

USER node
CMD ["node", "dist-runtime/jobs/reclaim-entrypoint.js"]
