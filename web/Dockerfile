FROM node:20-alpine AS build

WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install

COPY web ./
ARG VITE_API_BASE_URL
ARG VITE_BETTING_ENABLED
ARG VITE_APP_VERSION
ARG VITE_GIT_SHA
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_BETTING_ENABLED=${VITE_BETTING_ENABLED}
ENV VITE_APP_VERSION=${VITE_APP_VERSION}
ENV VITE_GIT_SHA=${VITE_GIT_SHA}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
