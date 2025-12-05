# Chrome Extension Token Refresh Implementation

## Overview

This implementation adds automatic Firebase ID token refresh functionality to the Chrome extension to handle authentication errors when tokens expire.

## Key Features

### 1. Automatic Token Refresh
- **Location**: `public/js/firebase/config.js` and `src/firebase/config.js`
- **Function**: `refreshFirebaseToken()`
- **Purpose**: Automatically refreshes Firebase ID tokens when they expire
- **Behavior**: 
  - Checks if a refresh is already in progress to prevent duplicate requests
  - Forces token refresh using Firebase's `getIdToken(true)`
  - Updates the stored user session with the new token
  - Handles errors gracefully

### 2. Token Expiration Checking
- **Location**: `public/js/firebase/config.js` and `src/firebase/config.js`
- **Function**: `isTokenExpired(token)`
- **Purpose**: Checks if a Firebase ID token is expired or about to expire
- **Behavior**:
  - Decodes JWT token to check expiration time
  - Considers tokens expired if they expire within 5 minutes (buffer time)
  - Returns `true` for invalid or unparseable tokens

### 3. Enhanced Token Retrieval
- **Location**: `public/js/background.js`
- **Function**: `getFirebaseIdToken()`
- **Purpose**: Gets Firebase ID token with automatic refresh if needed
- **Behavior**:
  - Checks token expiration before returning
  - Automatically refreshes expired tokens
  - Returns `null` if refresh fails

### 4. Authenticated Request Helper
- **Location**: `public/js/background.js`
- **Function**: `makeAuthenticatedRequest(url, options)`
- **Purpose**: Makes API calls with automatic token refresh on 401 errors
- **Behavior**:
  - Automatically adds Authorization header with current token
  - Retries failed requests (401 status) with refreshed token
  - Handles both proactive refresh and reactive refresh scenarios

## Updated API Functions

All API call functions now use `makeAuthenticatedRequest()` instead of manual `fetch()` calls:

- `postBookmark()` - Creates new bookmarks
- `searchBookmarkByUrl()` - Searches for bookmarks by URL
- `refreshBookmarksCache()` - Refreshes the bookmarks cache
- `deleteBookmark()` - Deletes bookmarks

## How It Works

### Proactive Token Refresh
1. Before making API calls, `getFirebaseIdToken()` checks if the current token is expired
2. If expired, it automatically refreshes the token using `refreshFirebaseToken()`
3. The refreshed token is used for the API call

### Reactive Token Refresh
1. If an API call returns a 401 (Unauthorized) status
2. `makeAuthenticatedRequest()` automatically attempts to refresh the token
3. The request is retried once with the new token
4. If the retry also fails, the error is propagated

### Token Storage
- Tokens are stored in Chrome's session storage under the `session_user` key
- The Firebase user object includes the `stsTokenManager` with the `accessToken`
- Refreshed tokens update the stored user object automatically

## Testing

A test script is provided at `test-token-refresh.js` that can be used to verify:
- Token expiration checking logic
- Token refresh functionality
- Integration with the background script

## Benefits

1. **Seamless User Experience**: Users won't see authentication errors due to expired tokens
2. **Automatic Recovery**: The extension automatically recovers from token expiration
3. **Reduced Support Issues**: Fewer authentication-related support requests
4. **Better Reliability**: API calls are more reliable with automatic token management

## Error Handling

The implementation includes comprehensive error handling:
- Graceful fallback when token refresh fails
- Proper error logging for debugging
- Prevention of infinite retry loops
- Clear error messages for different failure scenarios

## Security Considerations

- Tokens are refreshed using Firebase's secure `getIdToken(true)` method
- No sensitive information is logged
- Token refresh is rate-limited to prevent abuse
- Session storage is used appropriately for temporary token storage
