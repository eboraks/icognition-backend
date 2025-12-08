# Chrome Extension Improvements - December 2025

## Summary
This update includes two major improvements to the iCognition Chrome Extension:

### 1. Color Scheme Update
**Changed:** Updated the extension's header color to match the web application's design.

**Details:**
- Header background color changed from `bg-primary-800` (darker blue) to `bg-primary-500` (brighter blue)
- This creates a consistent visual experience between the web app and the extension
- The header now matches the web app's top navigation bar color

**Files Modified:**
- `chrome-extension/src/components/Popup.vue` - Updated header class

---

### 2. Backend Environment Switcher
**Added:** A new settings feature that allows users to switch between Staging and Development backend environments.

**Details:**
- Added a settings icon (cogwheel/pi-cog) in the extension header
- Settings dialog provides easy selection between:
  - **Staging**: `https://stg.api.icognition.ai`
  - **Development**: `http://localhost:8000`
- Environment preference is saved in Chrome's local storage
- Changes take effect immediately after saving
- Current environment is displayed in the settings dialog

**How to Use:**
1. Click the cogwheel icon (⚙️) in the extension header (visible when logged in)
2. Select your preferred backend environment
3. Click "Save & Apply"
4. The extension will immediately connect to the selected backend
5. All bookmarks and analysis will use the selected environment

**Files Modified:**
- `chrome-extension/src/components/Popup.vue`:
  - Added settings icon to header
  - Added Dialog component with environment selector
  - Added functions to load/save environment preference
  - Added styling for settings dialog

- `chrome-extension/src/composables/envVar.js`:
  - Updated to read environment preference from storage
  - Dynamically sets base URL based on user preference

- `chrome-extension/public/js/composables/envVar.js`:
  - Updated to read environment preference from storage
  - Ensures background script uses correct base URL

- `chrome-extension/public/js/background.js`:
  - Added `initializeBaseUrl()` function to load environment on startup
  - Added message handler for 'update-environment'
  - Updates base URL and reconnects SSE when environment changes

**Technical Details:**
- Environment preference is stored in `chrome.storage.local` under key `backendEnvironment`
- Values: `'staging'` (default) or `'development'`
- The setting persists across browser sessions
- When changed, the extension:
  1. Saves the preference
  2. Updates the base URL
  3. Clears cached data
  4. Reconnects to the new backend
  5. Refreshes current page data

---

## Testing Instructions

### Color Changes
1. Open the extension
2. Verify the header is a brighter blue (matches the web app)
3. Compare with the web app's header at `icognition.ai/library`

### Environment Switcher
1. **Login to the extension**
2. Click the settings icon (⚙️) in the header
3. Verify the settings dialog opens with both environment options
4. Select "Development" and click "Save & Apply"
5. Try bookmarking a page - it should hit `http://localhost:8000`
6. Open settings again and switch back to "Staging"
7. Verify the extension now connects to `https://stg.api.icognition.ai`
8. Close and reopen the extension - verify the setting persists

### Development Environment Requirements
To use the Development environment option:
- The backend must be running locally on `http://localhost:8000`
- Ensure CORS is properly configured to allow extension access
- The local backend should have the same endpoints as staging

---

## Build Instructions

After making these changes, rebuild the extension:

```bash
cd chrome-extension
npm run build:dev      # For development build
npm run build:staging  # For staging build
npm run build:prod     # For production build
```

Then reload the extension in Chrome:
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Reload" on the iCognition extension

---

## Future Enhancements

Potential improvements for future versions:
- Add a production environment option
- Display current environment in the extension badge
- Add environment indicator in the extension UI (not just in settings)
- Allow custom backend URL input for advanced users
- Add connection status indicator for each environment

