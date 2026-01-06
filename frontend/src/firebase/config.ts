// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { 
  getAuth, 
  createUserWithEmailAndPassword, 
  signInWithEmailAndPassword, 
  GoogleAuthProvider, 
  GithubAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  sendEmailVerification,
  updateProfile
} from "firebase/auth";
//import { getFirestore, Timestamp } from "firebase/firestore";

// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: import.meta.env.VITE_APP_FB_API_KEY,
  authDomain: "icognition-app.firebaseapp.com",
  projectId: "icognition-app",
  storageBucket: "icognition-app.appspot.com",
  messagingSenderId: "1022378307371",
  appId: "1:1022378307371:web:43a550bd3efad3ea7f9f6e",
  measurementId: "G-M1H60J2J4T"
};
const key = import.meta.env.VITE_APP_FB_API_KEY
console.log("Key: ",  key); 

// Only initialize Firebase if API key is provided (auth is enabled)
let app: any = null;
let auth: any = null;

if (key && key !== 'undefined') {
  // Initialize Firebase
  app = initializeApp(firebaseConfig);
  // Initialize Firebase Authentication and get a reference to the service
  auth = getAuth(app);
} else {
  console.log("Firebase disabled - no API key provided (DISABLE_AUTH mode)");
  // Create mock auth object for compatibility
  auth = {
    currentUser: null,
    onAuthStateChanged: (callback: any) => {
      callback(null);
      return () => {};
    }
  };
}

// Initialize Cloud Firestore and get a reference to the service
//const db = getFirestore(app);

export { 
  auth, 
  app, 
  createUserWithEmailAndPassword, 
  signInWithEmailAndPassword, 
  GoogleAuthProvider,
  GithubAuthProvider, 
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  sendEmailVerification,
  updateProfile
};