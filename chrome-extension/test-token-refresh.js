/**
 * Test script for Firebase token refresh functionality
 * This script can be run in the Chrome extension's background context
 * to test the token refresh mechanism
 */

// Import the functions we need to test
import { refreshFirebaseToken, isTokenExpired } from './public/js/firebase/config.js';

// Test function to verify token expiration checking
function testTokenExpiration() {
    console.log('Testing token expiration checking...');
    
    // Test with null token
    const nullResult = isTokenExpired(null);
    console.log('isTokenExpired(null):', nullResult); // Should be true
    
    // Test with invalid token
    const invalidResult = isTokenExpired('invalid.token.here');
    console.log('isTokenExpired(invalid):', invalidResult); // Should be true
    
    // Test with expired token (mock JWT with exp in the past)
    const expiredPayload = {
        exp: Math.floor(Date.now() / 1000) - 3600, // 1 hour ago
        iat: Math.floor(Date.now() / 1000) - 7200  // 2 hours ago
    };
    const expiredToken = 'header.' + btoa(JSON.stringify(expiredPayload)) + '.signature';
    const expiredResult = isTokenExpired(expiredToken);
    console.log('isTokenExpired(expired):', expiredResult); // Should be true
    
    // Test with valid token (mock JWT with exp in the future)
    const validPayload = {
        exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
        iat: Math.floor(Date.now() / 1000) - 300   // 5 minutes ago
    };
    const validToken = 'header.' + btoa(JSON.stringify(validPayload)) + '.signature';
    const validResult = isTokenExpired(validToken);
    console.log('isTokenExpired(valid):', validResult); // Should be false
    
    console.log('Token expiration tests completed');
}

// Test function to verify token refresh
async function testTokenRefresh() {
    console.log('Testing token refresh...');
    
    try {
        // This will only work if there's an authenticated user
        const newToken = await refreshFirebaseToken();
        console.log('Token refresh successful:', newToken ? 'Yes' : 'No');
        
        if (newToken) {
            // Verify the new token is not expired
            const isExpired = isTokenExpired(newToken);
            console.log('New token is expired:', isExpired);
        }
    } catch (error) {
        console.log('Token refresh failed (expected if no user):', error.message);
    }
    
    console.log('Token refresh test completed');
}

// Test function to verify getFirebaseIdToken with refresh
async function testGetFirebaseIdToken() {
    console.log('Testing getFirebaseIdToken with refresh...');
    
    try {
        // Import the function from background.js
        const { getFirebaseIdToken } = await import('./public/js/background.js');
        
        const token = await getFirebaseIdToken();
        console.log('getFirebaseIdToken result:', token ? 'Token obtained' : 'No token');
        
        if (token) {
            const isExpired = isTokenExpired(token);
            console.log('Retrieved token is expired:', isExpired);
        }
    } catch (error) {
        console.log('getFirebaseIdToken test failed:', error.message);
    }
    
    console.log('getFirebaseIdToken test completed');
}

// Run all tests
async function runAllTests() {
    console.log('Starting Firebase token refresh tests...');
    console.log('=====================================');
    
    testTokenExpiration();
    console.log('-------------------------------------');
    
    await testTokenRefresh();
    console.log('-------------------------------------');
    
    await testGetFirebaseIdToken();
    console.log('-------------------------------------');
    
    console.log('All tests completed!');
}

// Export for manual testing
export { testTokenExpiration, testTokenRefresh, testGetFirebaseIdToken, runAllTests };

// Auto-run tests if this script is executed directly
if (typeof window === 'undefined') {
    // Running in Node.js or Chrome extension context
    runAllTests();
}
