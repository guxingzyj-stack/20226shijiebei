FROM node:20-alpine AS build

WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install

COPY web ./
ARG VITE_API_BASE_URL
ARG VITE_BETTING_ENABLED
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_BETTING_ENABLED=${VITE_BETTING_ENABLED}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
