FROM node:20-alpine AS builder

ENV PATH=/app/node_modules/.bin:$PATH

WORKDIR /app

COPY ./package*.json ./

RUN npm ci

# Vite читает .env из settings/.envs/ (envDir в vite.config.ts)
# Для продакшена отредактируйте settings/.envs/.env перед сборкой
COPY ./ ./

RUN npm run build

FROM nginx:1.29.8-alpine

# Выбор nginx конфигурации в зависимости от STAGE
COPY ./docker/nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
