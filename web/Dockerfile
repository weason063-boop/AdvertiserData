# Frontend Dockerfile - Multi-stage
# Stage 1: Build
FROM node:20-alpine as build-stage

WORKDIR /app

# Copy package files and install dependencies
COPY web/package*.json ./
RUN npm install

# Copy source and build
COPY web/ .
RUN npm run build

# Stage 2: Production
FROM nginx:stable-alpine as production-stage

# Copy build output to nginx folder
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
