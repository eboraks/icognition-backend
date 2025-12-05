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

// Function to refresh Firebase ID token
async function refreshFirebaseToken() {
    if (tokenRefreshPromise) {
        return tokenRefreshPromise;
    }
    
    tokenRefreshPromise = new Promise(async (resolve, reject) => {
        try {
            const currentUser = auth.currentUser;
            if (!currentUser) {
                reject(new Error('No authenticated user'));
                return;
            }
            
            // Force refresh the ID token
            const newToken = await currentUser.getIdToken(true);
            
            // Serialize the updated user object properly for Chrome storage
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
            
            // Store updated user in session storage
            await chrome.storage.session.set({ session_user: updatedUser });
            
            console.log('Firebase token refreshed successfully');
            resolve(newToken);
        } catch (error) {
            console.error('Failed to refresh Firebase token:', error);
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
        console.error('Error checking token expiration:', error);
        return true; // If we can't parse the token, consider it expired
    }
}
  
export { firebase, auth, signOut, GoogleAuthProvider, signInWithCredential, onAuthStateChanged, refreshFirebaseToken, isTokenExpired }
