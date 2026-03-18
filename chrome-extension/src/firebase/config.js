// Import the functions you need from the SDKs you need
import { initializeApp } from 'firebase/app';
import { getAuth, signOut, GoogleAuthProvider, signInWithCredential, onAuthStateChanged } from 'firebase/auth';

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyAA1hrqYpKC6jcrjDyPtwKlDDpwDg4WM_U",
    authDomain: "icognition-app.firebaseapp.com",
    projectId: "icognition-app",
    storageBucket: "icognition-app.appspot.com",
    messagingSenderId: "1022378307371",
    appId: "1:1022378307371:web:43a550bd3efad3ea7f9f6e",
    measurementId: "G-M1H60J2J4T"
};

const firebase = initializeApp(firebaseConfig);
const auth = getAuth(firebase);

// Token refresh functionality
let tokenRefreshPromise = null;

// Refresh token via Firebase REST API using the stored refresh token.
// This works even when auth.currentUser is null (e.g., after service worker restart).
async function _refreshViaRestApi(refreshToken) {
    const response = await fetch(
        `https://securetoken.googleapis.com/v1/token?key=${firebaseConfig.apiKey}`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `grant_type=refresh_token&refresh_token=${encodeURIComponent(refreshToken)}`,
        }
    );

    if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(`Token refresh failed (${response.status}): ${errorBody}`);
    }

    const data = await response.json();
    return {
        idToken: data.id_token,
        refreshToken: data.refresh_token,
        expiresIn: parseInt(data.expires_in, 10),
    };
}

// Function to refresh Firebase ID token
async function refreshFirebaseToken() {
    if (tokenRefreshPromise) {
        return tokenRefreshPromise;
    }

    tokenRefreshPromise = new Promise(async (resolve, reject) => {
        try {
            // First, try using auth.currentUser (available when service worker hasn't restarted)
            const currentUser = auth.currentUser;
            if (currentUser) {
                const newToken = await currentUser.getIdToken(true);
                const updatedUser = {
                    uid: currentUser.uid,
                    email: currentUser.email,
                    displayName: currentUser.displayName,
                    photoURL: currentUser.photoURL,
                    emailVerified: currentUser.emailVerified,
                    stsTokenManager: {
                        accessToken: newToken,
                        refreshToken: currentUser.stsTokenManager.refreshToken,
                        expirationTime: currentUser.stsTokenManager.expirationTime
                    }
                };
                await chrome.storage.session.set({ session_user: updatedUser });
                console.log('Firebase token refreshed via SDK');
                resolve(newToken);
                return;
            }

            // Fallback: auth.currentUser is null (service worker restarted).
            // Use the stored refresh token to call Firebase REST API directly.
            const store = await chrome.storage.session.get(["session_user"]);
            const storedUser = store.session_user;
            if (!storedUser?.stsTokenManager?.refreshToken) {
                reject(new Error('No authenticated user and no refresh token available'));
                return;
            }

            console.log('Firebase SDK user unavailable, refreshing via REST API...');
            const result = await _refreshViaRestApi(storedUser.stsTokenManager.refreshToken);

            // Calculate new expiration time
            const expirationTime = Date.now() + result.expiresIn * 1000;

            // Update stored user with new tokens
            const updatedUser = {
                ...storedUser,
                stsTokenManager: {
                    accessToken: result.idToken,
                    refreshToken: result.refreshToken,
                    expirationTime: expirationTime,
                }
            };
            await chrome.storage.session.set({ session_user: updatedUser });
            console.log('Firebase token refreshed via REST API');
            resolve(result.idToken);
        } catch (error) {
            console.log('[ERROR]', 'Failed to refresh Firebase token:', error);
            reject(error);
        } finally {
            tokenRefreshPromise = null;
        }
    });

    return tokenRefreshPromise;
}

// Function to check if token is expired or about to expire
function isTokenExpired(token) {
    if (!token) return true;
    
    try {
        // Decode JWT token to check expiration
        const payload = JSON.parse(atob(token.split('.')[1]));
        const currentTime = Math.floor(Date.now() / 1000);
        const expirationTime = payload.exp;
        
        // Consider token expired if it expires within the next 5 minutes
        const bufferTime = 5 * 60; // 5 minutes in seconds
        return (expirationTime - currentTime) < bufferTime;
    } catch (error) {
        console.log('[ERROR]', 'Error checking token expiration:', error);
        return true; // If we can't parse the token, consider it expired
    }
}
  
export { firebase, auth, signOut, GoogleAuthProvider, signInWithCredential, onAuthStateChanged, refreshFirebaseToken, isTokenExpired }