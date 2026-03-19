FROM node:20-bookworm-slim
WORKDIR /app
COPY package*.json .
RUN npm ci --include=dev \
  && npm install --force --save-optional @rollup/rollup-linux-x64-gnu@4.59.0
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
