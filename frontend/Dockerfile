FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --include=dev \
  && npm install --force --save-optional \
     @rollup/rollup-linux-arm64-gnu \
     @rollup/rollup-linux-x64-gnu \
     @rollup/rollup-linux-arm64-musl \
     @rollup/rollup-linux-x64-musl
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]