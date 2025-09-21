from uuid import UUID
from app.log import get_logger
from app.db_connector import get_engine
import app.getters as getter
import hashlib
from typing import Dict, List, Optional
from app.models import Collection

logging = get_logger()

class CollectionsManager:
    """Manages collections of documents using their IDs"""
    
    def __init__(self):
        # Dictionary to store collections: {collection_id: Study_Collection}
        self._collections: Dict[str, Collection] = {}
    
    def create_or_get_collection(self, docs_ids: List[UUID], user_id: str) -> Collection:
        """
        Create a new collection or get an existing one based on source IDs.
        
        Args:
            source_ids: List of source document IDs
            user_id: User ID who owns the collection
            
        Returns:
            Study_Collection: The created or existing collection
        """
        # Generate collection ID from source IDs
        docs_ids_str = [str(doc_id) for doc_id in docs_ids]
        collection_id = self._create_id_from_strings(docs_ids_str)
        
        # Check if collection already exists
        if collection_id in self._collections:
            return self._collections[collection_id]
        
        # Create new collection
        collection = Collection(
            id=collection_id,
            name=f"Collection {collection_id[:8]}",  # Use first 8 chars of hash as name
            user_id=user_id,
            status="PENDING",
            documents_ids=docs_ids_str
        )
        
        # Store the collection
        self._collections[collection_id] = collection
        
        return collection
    
    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """
        Get a collection by its ID
        
        Args:
            collection_id: The collection ID to look up
            
        Returns:
            Optional[Study_Collection]: The collection if found, None otherwise
        """
        return self._collections.get(collection_id)
    
    def remove_collection(self, collection_id: str) -> bool:
        """
        Remove a collection from the manager
        
        Args:
            collection_id: The collection ID to remove
            
        Returns:
            bool: True if collection was removed, False if not found
        """
        if collection_id in self._collections:
            del self._collections[collection_id]
            return True
        return False
    
    @staticmethod
    def _create_id_from_strings(string_list: List[str]) -> str:
        """
        Generates a unique ID from a list of strings using SHA-256 hashing.

        Args:
            string_list: A list of strings.

        Returns:
            A hexadecimal string representing the hash of the concatenated strings.
        """
        # Sort the strings to ensure consistent ordering
        sorted_strings = sorted(string_list)
        
        # Concatenate the strings
        combined_string = "".join(sorted_strings)
        
        # Hash the combined string using SHA-256
        hash_object = hashlib.sha256(combined_string.encode())
        
        # Return the hexadecimal representation of the hash
        return hash_object.hexdigest()

# Create a global instance of the collections manager
collections_manager = CollectionsManager()

