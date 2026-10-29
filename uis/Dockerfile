FROM node:22-alpine

RUN apk add --no-cache bash libc6-compat

WORKDIR /app

COPY website/package.json ./uis/website/package.json
RUN cd /app/uis/website && npm install --no-audit --no-fund

COPY backoffice/package.json ./uis/backoffice/package.json
RUN cd /app/uis/backoffice && npm install --no-audit --no-fund

COPY website ./uis/website
COPY backoffice ./uis/backoffice
COPY start.sh ./uis/start.sh
COPY --from=repo /packages/shared ./packages/shared
COPY --from=repo /src ./src

ARG NEXT_PUBLIC_INVENTORY_API_URL=http://api:8000
ENV NEXT_PUBLIC_INVENTORY_API_URL=${NEXT_PUBLIC_INVENTORY_API_URL}
ENV NODE_ENV=production

WORKDIR /app/uis/website
RUN npm run build

WORKDIR /app/uis/backoffice
RUN npm run build

EXPOSE 3000 3001

CMD ["bash", "/app/uis/start.sh"]