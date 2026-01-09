"""
Wikidata Service for entity anchoring and enrichment.
Provides methods to search Wikidata and retrieve entity details.
"""

from typing import List, Optional, Dict, Any
import httpx
from pydantic import BaseModel
from app.utils.logging import get_logger

logger = get_logger(__name__)

class WikidataEntity(BaseModel):
    """Data model for a Wikidata entity"""
    wikidata_id: str
    label: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    aliases: List[str] = []

class WikidataService:
    """
    Service for interacting with Wikidata API.
    Used for anchoring local entities to global Wikidata records.
    """
    
    def __init__(self):
        self.api_url = "https://www.wikidata.org/w/api.php"
        self.user_agent = "iCognition/1.0 (https://icognition.ai; eliran@icognition.ai) httpx/0.27.0"
    
    async def search_entities(self, query: str, limit: int = 5) -> List[WikidataEntity]:
        """
        Search for entities on Wikidata by name/label.
        
        Args:
            query: Search string
            limit: Maximum number of results
            
        Returns:
            List of WikidataEntity objects
        """
        if not query or not query.strip():
            return []
            
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "search": query,
            "limit": limit,
        }
        
        headers = {"User-Agent": self.user_agent}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("search", []):
                    entity = WikidataEntity(
                        wikidata_id=item["id"],
                        label=item.get("label"),
                        description=item.get("description"),
                        url=item.get("url") or f"https://www.wikidata.org/wiki/{item['id']}",
                        aliases=item.get("aliases", [])
                    )
                    results.append(entity)
                    
                return results
                
        except Exception as e:
            logger.error(f"Error searching Wikidata for '{query}': {e}")
            return []

    async def get_entity_details(self, wikidata_id: str) -> Optional[WikidataEntity]:
        """
        Get detailed information for a specific Wikidata ID.
        
        Args:
            wikidata_id: The Q-number (e.g., 'Q312' for Apple Inc.)
            
        Returns:
            WikidataEntity object or None if not found
        """
        params = {
            "action": "wbgetentities",
            "format": "json",
            "languages": "en",
            "ids": wikidata_id,
        }
        
        headers = {"User-Agent": self.user_agent}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                entities = data.get("entities", {})
                if wikidata_id not in entities:
                    return None
                    
                item = entities[wikidata_id]
                
                # Extract label and description from nested structures
                label = item.get("labels", {}).get("en", {}).get("value")
                description = item.get("descriptions", {}).get("en", {}).get("value")
                
                # Extract aliases
                aliases_data = item.get("aliases", {}).get("en", [])
                aliases = [a.get("value") for a in aliases_data if "value" in a]
                
                return WikidataEntity(
                    wikidata_id=wikidata_id,
                    label=label,
                    description=description,
                    url=f"https://www.wikidata.org/wiki/{wikidata_id}",
                    aliases=aliases
                )
                
        except Exception as e:
            logger.error(f"Error fetching Wikidata details for {wikidata_id}: {e}")
            return None

# Global instance
_wikidata_service = WikidataService()

def get_wikidata_service() -> WikidataService:
    """Get the global Wikidata service instance"""
    return _wikidata_service
