# syntax=docker/dockerfile:1.7
#
# Testlyn web Dockerfile.
# Build context MUST be the repo root (pnpm workspace) so the build can
# resolve @testlyn/shared and @testlyn/ui from packages/.
#   docker build -f apps/web/Dockerfile -t testlyn-web .

FROM node:24-alpine AS base
RUN apk add --no-cache libc6-compat
WORKDIR /repo

# ─── Stage 1: build ──────────────────────────────────────────────────────────
FROM base AS builder
RUN corepack enable
COPY . .
RUN pnpm install --frozen-lockfile
RUN pnpm --filter=@testlyn/web build

# ─── Stage 2: runtime (Next standalone) ──────────────────────────────────────
FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=8080 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 8080

CMD ["node", "apps/web/server.js"]
