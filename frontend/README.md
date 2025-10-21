# iCognition Frontend

Vue.js 3 frontend application for the iCognition document analysis platform.

## 🏗️ Architecture

- **Framework**: Vue.js 3 with Composition API
- **Language**: TypeScript
- **UI Library**: PrimeVue with PrimeFlex
- **Build Tool**: Vite
- **State Management**: Pinia
- **HTTP Client**: Axios
- **Authentication**: Firebase (optional)
- **Styling**: Tailwind CSS + PrimeVue themes

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- npm
- Backend server running (see backend README)

### 1. Install Dependencies

```bash
npm install
```

### 2. Environment Configuration

Edit `src/config/environment.ts`:

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',  // Backend API URL
  
  // Firebase configuration (optional - only needed if using authentication)
  firebase: {
    apiKey: 'your-api-key',
    authDomain: 'your-project.firebaseapp.com',
    projectId: 'your-project-id',
    storageBucket: 'your-project.appspot.com',
    messagingSenderId: '123456789',
    appId: 'your-app-id'
  }
};
```

### 3. Start Development Server

```bash
# For local development (no authentication)
npm run local

# For development with authentication
npm run dev

# For staging environment
npm run staging
```

### 4. Access the Application

- **Local**: http://localhost:8080
- **Development**: http://localhost:8080 (with auth)
- **Staging**: http://localhost:8080 (staging config)

## 🔐 Authentication Setup

### Option 1: Disable Authentication (Recommended for Development)

1. Set `DISABLE_AUTH=true` in your backend `.env` file
2. Use `npm run local` to start the frontend
3. No Firebase configuration needed

### Option 2: Enable Firebase Authentication

1. **Create Firebase Project**:
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Create a new project
   - Enable Authentication with your preferred providers

2. **Get Firebase Configuration**:
   - Go to Project Settings → General
   - Scroll down to "Your apps"
   - Add a web app or use existing configuration

3. **Configure Frontend**:
   - Update `src/config/environment.ts` with your Firebase config
   - Use `npm run dev` instead of `npm run local`

4. **Test Authentication**:
   - The app will show login/logout buttons
   - Check browser console for authentication status

## 🧪 Testing

### Run Tests

```bash
# Run unit tests (if configured)
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

### Linting

```bash
# Lint JavaScript/TypeScript files
npm run lint:js

# Fix linting issues
npm run lint:js -- --fix

# Lint CSS/SCSS files
npm run lint:css
```

### Type Checking

```bash
# Check TypeScript types
npm run type-check

# Build and check types
npm run build
```

## 📚 Project Structure

```
frontend/
├── src/
│   ├── components/          # Reusable Vue components
│   │   ├── common/         # Common UI components
│   │   ├── library/        # Library-specific components
│   │   └── forms/          # Form components
│   ├── views/              # Page views/routes
│   │   ├── Library.vue     # Main library view
│   │   ├── DocumentContainer.vue  # Document view
│   │   └── ...
│   ├── services/           # API services
│   │   ├── api.ts          # API client configuration
│   │   ├── auth.ts         # Authentication service
│   │   └── ...
│   ├── stores/             # Pinia stores
│   │   ├── auth.ts         # Authentication store
│   │   ├── library.ts      # Library data store
│   │   └── ...
│   ├── composables/        # Vue composables
│   │   ├── useAuth.ts      # Authentication composable
│   │   ├── useApi.ts       # API composable
│   │   └── ...
│   ├── config/             # Configuration files
│   │   └── environment.ts  # Environment configuration
│   ├── firebase/           # Firebase configuration
│   │   ├── config.ts       # Firebase config
│   │   └── auth.ts         # Firebase auth setup
│   ├── router/             # Vue Router configuration
│   │   └── index.ts        # Route definitions
│   ├── assets/             # Static assets
│   │   ├── images/         # Image files
│   │   └── styles/         # Global styles
│   ├── theme/              # PrimeVue theme configuration
│   ├── App.vue             # Root component
│   └── main.ts             # Application entry point
├── public/                 # Public static files
├── package.json            # Dependencies and scripts
├── vite.config.js          # Vite configuration
├── tailwind.config.js      # Tailwind CSS configuration
└── tsconfig.json           # TypeScript configuration
```

## 🛠️ Development

### Available Scripts

```bash
# Development servers
npm run local          # Local development (no auth)
npm run dev            # Development with auth
npm run staging        # Staging environment

# Build
npm run build          # Production build
npm run preview        # Preview production build

# GCP deployment
npm run gcp-dev        # GCP development mode
npm run dev-build      # GCP development build

# Code quality
npm run lint:js        # Lint JavaScript/TypeScript
npm run type-check     # TypeScript type checking
```

### Adding New Components

1. **Create Component**:
   ```vue
   <!-- src/components/common/NewComponent.vue -->
   <template>
     <div class="new-component">
       <h2>{{ title }}</h2>
       <p>{{ description }}</p>
     </div>
   </template>
   
   <script setup lang="ts">
   interface Props {
     title: string
     description?: string
   }
   
   defineProps<Props>()
   </script>
   
   <style scoped>
   .new-component {
     @apply p-4 border rounded-lg;
   }
   </style>
   ```

2. **Export Component**:
   ```typescript
   // src/components/common/index.ts
   export { default as NewComponent } from './NewComponent.vue'
   ```

### Adding New Views

1. **Create View**:
   ```vue
   <!-- src/views/NewView.vue -->
   <template>
     <div class="new-view">
       <h1>New View</h1>
       <!-- Your content here -->
     </div>
   </template>
   
   <script setup lang="ts">
   // Component logic
   </script>
   ```

2. **Add Route**:
   ```typescript
   // src/router/index.ts
   import NewView from '@/views/NewView.vue'
   
   const routes = [
     // ... existing routes
     {
       path: '/new-view',
       name: 'NewView',
       component: NewView
     }
   ]
   ```

### API Integration

1. **Create Service**:
   ```typescript
   // src/services/newService.ts
   import { api } from './api'
   
   export interface NewItem {
     id: string
     name: string
     description?: string
   }
   
   export const newService = {
     async getItems(): Promise<NewItem[]> {
       const response = await api.get('/new-items/')
       return response.data
     },
   
     async createItem(item: Omit<NewItem, 'id'>): Promise<NewItem> {
       const response = await api.post('/new-items/', item)
       return response.data
     }
   }
   ```

2. **Use in Component**:
   ```vue
   <script setup lang="ts">
   import { newService, type NewItem } from '@/services/newService'
   import { ref, onMounted } from 'vue'
   
   const items = ref<NewItem[]>([])
   
   onMounted(async () => {
     items.value = await newService.getItems()
   })
   </script>
   ```

### State Management with Pinia

1. **Create Store**:
   ```typescript
   // src/stores/newStore.ts
   import { defineStore } from 'pinia'
   import { newService, type NewItem } from '@/services/newService'
   
   export const useNewStore = defineStore('new', () => {
     const items = ref<NewItem[]>([])
     const loading = ref(false)
   
     const fetchItems = async () => {
       loading.value = true
       try {
         items.value = await newService.getItems()
       } finally {
         loading.value = false
       }
     }
   
     return {
       items,
       loading,
       fetchItems
     }
   })
   ```

2. **Use in Component**:
   ```vue
   <script setup lang="ts">
   import { useNewStore } from '@/stores/newStore'
   
   const newStore = useNewStore()
   
   onMounted(() => {
     newStore.fetchItems()
   })
   </script>
   ```

## 🎨 Styling

### PrimeVue Components

```vue
<template>
  <div>
    <!-- PrimeVue Button -->
    <Button label="Click Me" @click="handleClick" />
    
    <!-- PrimeVue DataTable -->
    <DataTable :value="items" :paginator="true" :rows="10">
      <Column field="name" header="Name" />
      <Column field="description" header="Description" />
    </DataTable>
    
    <!-- PrimeVue Dialog -->
    <Dialog v-model:visible="showDialog" header="Dialog Title">
      <p>Dialog content</p>
    </Dialog>
  </div>
</template>
```

### Tailwind CSS Classes

```vue
<template>
  <div class="flex items-center justify-between p-4 bg-white rounded-lg shadow-md">
    <h2 class="text-xl font-semibold text-gray-800">Title</h2>
    <Button class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
      Action
    </Button>
  </div>
</template>
```

### Custom Styles

```vue
<style scoped>
.custom-component {
  @apply p-4 border rounded-lg;
}

.custom-component:hover {
  @apply shadow-md;
}
</style>
```

## 🔧 Configuration

### Environment Modes

The application supports different environment modes:

- **local**: No authentication, local backend
- **dev**: With authentication, development backend
- **staging**: Staging environment configuration
- **production**: Production environment

### Vite Configuration

```javascript
// vite.config.js
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
```

### TypeScript Configuration

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

## 🚨 Troubleshooting

### Common Issues

1. **Backend Connection Error**:
   ```bash
   # Check if backend is running
   curl http://localhost:8000/health
   
   # Update API URL in environment.ts
   apiUrl: 'http://localhost:8000'
   ```

2. **Firebase Authentication Issues**:
   - Verify Firebase configuration in `environment.ts`
   - Check browser console for Firebase errors
   - Ensure Firebase project has authentication enabled

3. **Build Errors**:
   ```bash
   # Clear node_modules and reinstall
   rm -rf node_modules
   npm install
   
   # Clear Vite cache
   rm -rf .vite
   ```

4. **TypeScript Errors**:
   ```bash
   # Check TypeScript configuration
   npm run type-check
   
   # Update tsconfig.json if needed
   ```

### Debug Mode

```bash
# Run with debug logging
DEBUG=vite:* npm run dev

# Check browser console for errors
# Use Vue DevTools browser extension
```

## 🚀 Deployment

### Development Build

```bash
# Build for development
npm run dev-build

# Preview build locally
npm run preview
```

### Production Build

```bash
# Build for production
npm run build

# The dist/ folder contains the built application
```

### Firebase Deployment

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Login to Firebase
firebase login

# Deploy to Firebase Hosting
firebase deploy
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM node:18-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

EXPOSE 8080
CMD ["npm", "run", "preview"]
```

## 📊 Performance

### Optimization Tips

1. **Code Splitting**:
   ```typescript
   // Lazy load routes
   const Library = () => import('@/views/Library.vue')
   ```

2. **Component Optimization**:
   ```vue
   <script setup lang="ts">
   // Use shallowRef for large objects
   import { shallowRef } from 'vue'
   
   const largeData = shallowRef([])
   </script>
   ```

3. **Image Optimization**:
   ```vue
   <template>
     <!-- Use lazy loading for images -->
     <img :src="imageUrl" loading="lazy" alt="Description" />
   </template>
   ```

### Bundle Analysis

```bash
# Analyze bundle size
npm run build -- --analyze

# Check bundle composition
npx vite-bundle-analyzer dist/
```

## 📄 License

This project is proprietary software. All rights reserved.