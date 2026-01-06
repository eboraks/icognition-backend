FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code and config files
COPY . .

# Expose port
EXPOSE 8080

# Start development server (local mode - no auth)
CMD ["npm", "run", "local"]

