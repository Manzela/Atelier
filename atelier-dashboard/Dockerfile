# Atelier Studio dashboard — Next.js 16 standalone for Cloud Run (AT-083).
#
# Build context is the repo root (the npm workspace @atelier/workspace); the
# root lockfile installs the atelier-dashboard workspace. Public build-time
# config (NEXT_PUBLIC_*) is inlined into the client bundle at build, so it is
# passed as build args (these are public client-side identifiers, not secrets).
#
# Build: gcloud builds submit --config atelier-dashboard/cloudbuild.yaml .

FROM node:22.13.0-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY atelier-dashboard/package.json ./atelier-dashboard/
RUN npm ci

FROM node:22.13.0-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY atelier-dashboard ./atelier-dashboard

ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
ARG NEXT_PUBLIC_A2UI_RENDER=0
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID \
    NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=$NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET \
    NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=$NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID \
    NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID \
    NEXT_PUBLIC_A2UI_RENDER=$NEXT_PUBLIC_A2UI_RENDER \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/atelier-dashboard
RUN npm run build

FROM node:22.13.0-slim AS production
WORKDIR /app
ENV NODE_ENV=production \
    PORT=8080 \
    NEXT_TELEMETRY_DISABLED=1
RUN groupadd --gid 1000 nodeapp \
    && useradd --uid 1000 --gid nodeapp --create-home nodeapp

# The standalone bundle mirrors the workspace tree (outputFileTracingRoot is the
# workspace root), so the server entry is atelier-dashboard/server.js.
COPY --from=build --chown=nodeapp:nodeapp /app/atelier-dashboard/.next/standalone ./
COPY --from=build --chown=nodeapp:nodeapp /app/atelier-dashboard/.next/static ./atelier-dashboard/.next/static
COPY --from=build --chown=nodeapp:nodeapp /app/atelier-dashboard/public ./atelier-dashboard/public

USER nodeapp
EXPOSE 8080
CMD ["node", "atelier-dashboard/server.js"]
