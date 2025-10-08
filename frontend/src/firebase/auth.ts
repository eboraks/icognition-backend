import { 
  auth, 
  createUserWithEmailAndPassword, 
  signInWithEmailAndPassword, 
  GoogleAuthProvider,
  GithubAuthProvider,
  signInWithPopup,
  signOut,
  sendEmailVerification,
  updateProfile
} from './config';

// Password validation function
export function validatePassword(password: string) {
  const minLength = 12;
  const hasUpperCase = /[A-Z]/.test(password);
  const hasLowerCase = /[a-z]/.test(password);
  const hasNumbers = /\d/.test(password);
  const hasSpecialChars = /[!@#$%^&*(),.?":{}|<>]/.test(password);
  
  const errors = [];
  if (password.length < minLength) errors.push(`Password must be at least ${minLength} characters`);
  if (!hasUpperCase) errors.push("Password must contain at least one uppercase letter");
  if (!hasLowerCase) errors.push("Password must contain at least one lowercase letter");
  if (!hasNumbers) errors.push("Password must contain at least one number");
  if (!hasSpecialChars) errors.push("Password must contain at least one special character");
  
  return { valid: errors.length === 0, errors };
}

// Enhanced user registration
export async function registerUser(email: string, password: string, displayName: string) {
  try {
    // Validate password first
    const passwordValidation = validatePassword(password);
    if (!passwordValidation.valid) {
      throw new Error(passwordValidation.errors.join(', '));
    }

    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    
    // Update profile with display name
    await updateProfile(userCredential.user, { displayName });
    
    // Send email verification
    await sendEmailVerification(userCredential.user);
    
    return userCredential.user;
  } catch (error: any) {
    console.error("Error registering user:", error);
    throw error;
  }
}

// Enhanced user login
export async function loginUser(email: string, password: string) {
  try {
    const userCredential = await signInWithEmailAndPassword(auth, email, password);
    
    // Check if email is verified
    if (!userCredential.user.emailVerified) {
      throw new Error("Please verify your email before logging in. Check your inbox.");
    }
    
    return userCredential.user;
  } catch (error: any) {
    console.error("Error logging in:", error);
    throw error;
  }
}

// Google authentication
export async function signInWithGoogle() {
  const provider = new GoogleAuthProvider();
  try {
    const result = await signInWithPopup(auth, provider);
    return result.user;
  } catch (error: any) {
    console.error("Error signing in with Google:", error);
    throw error;
  }
}

// GitHub authentication
export async function signInWithGithub() {
  const provider = new GithubAuthProvider();
  try {
    const result = await signInWithPopup(auth, provider);
    return result.user;
  } catch (error: any) {
    console.error("Error signing in with GitHub:", error);
    throw error;
  }
}

// Logout function
export async function logoutUser() {
  try {
    await signOut(auth);
  } catch (error: any) {
    console.error("Error signing out:", error);
    throw error;
  }
}

// Send email verification
export async function sendVerificationEmail(user: any) {
  try {
    await sendEmailVerification(user);
    return true;
  } catch (error: any) {
    console.error("Error sending verification email:", error);
    throw error;
  }
}

// Check if email verification is required
export function requireVerifiedEmail(user: any) {
  if (!user.emailVerified) {
    throw new Error("Email verification required. Please check your inbox.");
  }
}
