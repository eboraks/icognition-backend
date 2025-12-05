# iCognition Chrome Extension

A Chrome extension that provides TLDR summaries and other information about web articles in a side panel. The extension integrates with the iCognition backend API to analyze and bookmark web content.

## Features

- **Article Analysis**: Get TLDR summaries and key insights from web articles
- **Bookmark Management**: Save and organize articles for later reference
- **Side Panel Interface**: Clean, accessible interface in Chrome's side panel
- **Firebase Authentication**: Secure user authentication with automatic token refresh
- **Real-time Updates**: WebSocket connection for live updates
- **Content Highlighting**: Highlight and interact with web page content

## Prerequisites

- Node.js (version 16 or higher)
- npm or yarn package manager
- Chrome browser (for testing)

## Installation & Setup

### 1. Clone and Install Dependencies

```bash
# Navigate to the chrome-extension directory
cd chrome-extension

# Install dependencies
npm install
```

### 2. Environment Configuration

Create a `.env` file in the chrome-extension directory with the following variables:

```env
VITE_BASE_URL=http://localhost:8000
```

Replace `http://localhost:8000` with your actual backend API URL.

### 3. Build the Extension

```bash
# Build for development
npm run dev

# Build for production
npm run build
```

The built extension files will be in the `dist/` directory.

## Loading the Extension in Chrome

### Development Mode

1. **Open Chrome Extensions Page**
   - Navigate to `chrome://extensions/`
   - Or go to Chrome Menu → More Tools → Extensions

2. **Enable Developer Mode**
   - Toggle the "Developer mode" switch in the top-right corner

3. **Load Unpacked Extension**
   - Click "Load unpacked" button
   - Select the `dist/` directory from your chrome-extension folder
   - The extension should now appear in your extensions list

4. **Pin the Extension**
   - Click the puzzle piece icon in Chrome's toolbar
   - Find "iCognition" and click the pin icon to keep it visible

### Production Mode

For production deployment, you'll need to:

1. **Build for Production**
   ```bash
   npm run build
   ```

2. **Package the Extension**
   - Zip the contents of the `dist/` directory
   - Upload to Chrome Web Store for distribution

## Usage

### First Time Setup

1. **Sign In**: Click the iCognition extension icon and sign in with your Google account
2. **Grant Permissions**: Allow the extension to access web pages and storage

### Using the Extension

1. **Open Side Panel**: Click the iCognition extension icon to open the side panel
2. **Analyze Articles**: Navigate to any web article and the extension will automatically analyze it
3. **Bookmark Content**: Use the bookmark button to save articles for later
4. **View Bookmarks**: Access your saved bookmarks in the side panel

### Keyboard Shortcuts

- The extension supports Chrome's command API for custom keyboard shortcuts
- Check `chrome://extensions/shortcuts` to configure shortcuts

## Development

### Project Structure

```
chrome-extension/
├── src/                    # Source files
│   ├── components/         # Vue components
│   ├── composables/        # Vue composables
│   ├── firebase/          # Firebase configuration
│   └── main.js            # Entry point
├── public/                # Static assets
│   ├── js/                # Built JavaScript files
│   ├── css/               # Stylesheets
│   ├── icons/             # Extension icons
│   └── manifest.json      # Extension manifest
├── dist/                  # Built extension (after npm run build)
├── package.json           # Dependencies and scripts
└── vite.config.js         # Vite configuration
```

### Available Scripts

```bash
# Development build with hot reload
npm run dev

# Production build
npm run build

# Preview production build
npm run preview

# Lint code
npm run lint
```

### Firebase Configuration

The extension uses Firebase for authentication. The configuration is located in:
- `src/firebase/config.js` (source)
- `public/js/firebase/config.js` (built)

### Token Refresh System

The extension includes automatic Firebase token refresh functionality:
- Tokens are automatically refreshed when they expire
- API calls retry with refreshed tokens on 401 errors
- See `TOKEN_REFRESH_README.md` for detailed information

## Troubleshooting

### Common Issues

1. **Extension Not Loading**
   - Ensure you're loading the `dist/` directory, not the root directory
   - Check that all dependencies are installed (`npm install`)
   - Verify the build completed successfully (`npm run build`)

2. **Authentication Errors**
   - Check that Firebase configuration is correct
   - Ensure the backend API is running and accessible
   - Verify the `VITE_BASE_URL` environment variable is set correctly

3. **API Connection Issues**
   - Check network connectivity
   - Verify the backend API URL in your `.env` file
   - Check browser console for error messages

4. **Permission Errors**
   - Ensure the extension has necessary permissions in `manifest.json`
   - Check Chrome's extension permissions page

### Debug Mode

To enable debug logging:

1. Open Chrome DevTools (F12)
2. Go to Console tab
3. Look for iCognition extension logs
4. Check the Extension's background page console for additional logs

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Check the troubleshooting section above
- Review the browser console for error messages
- Contact the development team
