"""
Firebase Authentication service for FastAPI backend.
Handles Firebase Admin SDK initialization and token verification.
"""

import os
import json
from typing import Optional, Dict, Any
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, status
from app.log import get_logger

logger = get_logger(__name__)

class FirebaseAuth:
    """Firebase Authentication service for verifying ID tokens and managing users."""
    
    def __init__(self):
        """Initialize Firebase Admin SDK."""
        self._app = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK with service account credentials."""
        try:
            # Check if Firebase is already initialized
            if firebase_admin._apps:
                self._app = firebase_admin.get_app()
                logger.info("Firebase Admin SDK already initialized")
                return
            
            # Try to get credentials from environment variable (JSON string)
            firebase_credentials_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
            if firebase_credentials_json:
                try:
                    credentials_dict = json.loads(firebase_credentials_json)
                    cred = credentials.Certificate(credentials_dict)
                    logger.info("Using Firebase credentials from environment variable")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Firebase credentials JSON: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Invalid Firebase credentials format"
                    )
            else:
                # Try to get credentials from file path
                firebase_credentials_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
                if firebase_credentials_path and os.path.exists(firebase_credentials_path):
                    cred = credentials.Certificate(firebase_credentials_path)
                    logger.info(f"Using Firebase credentials from file: {firebase_credentials_path}")
                else:
                    logger.error("No Firebase credentials found. Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_PATH")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Firebase credentials not configured"
                    )
            
            # Initialize Firebase Admin SDK
            self._app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Firebase initialization failed: {str(e)}"
            )
    
    async def verify_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify a Firebase ID token and return the decoded token.
        
        Args:
            id_token: The Firebase ID token to verify
            
        Returns:
            Dict containing the decoded token data including uid, email, etc.
            
        Raises:
            HTTPException: If token is invalid or verification fails
        """
        try:
            # Verify the ID token
            decoded_token = auth.verify_id_token(id_token)
            logger.info(f"Successfully verified token for user: {decoded_token.get('uid')}")
            return decoded_token
        
        except auth.ExpiredIdTokenError:
            logger.warning("ID token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ID token has expired"
            )
        except auth.RevokedIdTokenError:
            logger.warning("ID token has been revoked")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ID token has been revoked"
            )
        except auth.InvalidIdTokenError as e:
            logger.warning(f"Invalid ID token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid ID token"
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying ID token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token verification failed"
            )
    
    async def get_user_by_uid(self, uid: str) -> Optional[auth.UserRecord]:
        """
        Get Firebase user record by UID.
        
        Args:
            uid: Firebase user UID
            
        Returns:
            UserRecord if found, None otherwise
        """
        try:
            user_record = auth.get_user(uid)
            return user_record
        except auth.UserNotFoundError:
            logger.warning(f"User not found: {uid}")
            return None
        except Exception as e:
            logger.error(f"Error getting user {uid}: {e}")
            return None
    
    async def create_user(self, email: str, password: str, display_name: str = None) -> auth.UserRecord:
        """
        Create a new Firebase user.
        
        Args:
            email: User email
            password: User password
            display_name: Optional display name
            
        Returns:
            Created UserRecord
            
        Raises:
            HTTPException: If user creation fails
        """
        try:
            user_data = {
                'email': email,
                'password': password,
                'email_verified': False
            }
            if display_name:
                user_data['display_name'] = display_name
            
            user_record = auth.create_user(**user_data)
            logger.info(f"Created new user: {user_record.uid}")
            return user_record
            
        except auth.EmailAlreadyExistsError:
            logger.warning(f"Email already exists: {email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User creation failed: {str(e)}"
            )
    
    async def update_user(self, uid: str, **kwargs) -> auth.UserRecord:
        """
        Update Firebase user record.
        
        Args:
            uid: Firebase user UID
            **kwargs: Fields to update
            
        Returns:
            Updated UserRecord
        """
        try:
            user_record = auth.update_user(uid, **kwargs)
            logger.info(f"Updated user: {uid}")
            return user_record
        except auth.UserNotFoundError:
            logger.warning(f"User not found for update: {uid}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        except Exception as e:
            logger.error(f"Failed to update user {uid}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User update failed: {str(e)}"
            )
    
    async def delete_user(self, uid: str) -> None:
        """
        Delete Firebase user.
        
        Args:
            uid: Firebase user UID
        """
        try:
            auth.delete_user(uid)
            logger.info(f"Deleted user: {uid}")
        except auth.UserNotFoundError:
            logger.warning(f"User not found for deletion: {uid}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        except Exception as e:
            logger.error(f"Failed to delete user {uid}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User deletion failed: {str(e)}"
            )

# Global Firebase Auth instance
firebase_auth = FirebaseAuth()
