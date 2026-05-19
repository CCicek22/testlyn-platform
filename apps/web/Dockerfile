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

# NEXT_PUBLIC_* values must be present at build time — Next bakes them into
# the static bundle. Defaults are CI-safe placeholders; the workflow passes
# real values from GitHub secrets via docker/build-push-action build-args.
ARG NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSyDUMMY_BUILD_PLACEHOLDER
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=placeholder.firebaseapp.com
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID=placeholder
ARG NEXT_PUBLIC_FIREBASE_APP_ID=1:000:web:placeholder
ARG NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=placeholder.firebasestorage.app
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=000000000000
ARG NEXT_PUBLIC_API_BASE_URL=https://api.dev.testlyn.example.com
ARG NEXT_PUBLIC_SITE_URL=https://dev.testlyn.example.com
ARG NEXT_PUBLIC_CHAT_BASE_URL=https://chat.dev.testlyn.example.com
# Always default to false — CI must explicitly pass true only for dev/test
# builds that require bypass. Production CI passes false (see ci-web.yml).
ARG NEXT_PUBLIC_DEV_AUTH_BYPASS=false

ENV NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID \
    NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID \
    NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=$NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET \
    NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=$NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_CHAT_BASE_URL=$NEXT_PUBLIC_CHAT_BASE_URL \
    NEXT_PUBLIC_DEV_AUTH_BYPASS=$NEXT_PUBLIC_DEV_AUTH_BYPASS

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
