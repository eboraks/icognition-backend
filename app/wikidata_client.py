import aiohttp
import asyncio
import logging
from typing import Optional, List
from pydantic import BaseModel


logging.basicConfig(level=logging.INFO)


class WikidataSearchResult(BaseModel):
    id: str
    label: str
    description: Optional[str] = "No description"
    aliases: List[str] = []
    sitelinks: List[str] = []
    instance_of: List[str] = []


class WikidataClient:
    def __init__(self):
        self.api_url = "https://www.wikidata.org/w/api.php"

    async def text_search(
        self, search_text: str, limit: int = 10
    ) -> list[WikidataSearchResult]:
        logging.info(f"Searching for entities with text: {search_text}")
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "search": search_text,
            "limit": limit,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(self.api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []
                    for item in data["search"]:
                        result = WikidataSearchResult(
                            id=item["id"],
                            label=item["label"],
                            description=item.get("description", "No description"),
                            aliases=item.get("aliases", []),
                            sitelinks=item.get("sitelinks", []),
                            instance_of=item.get("concepts", []),
                        )
                        results.append(result)
                    return results
                else:
                    response.raise_for_status()

    async def search_by_label(
        self, label: str, limit: int = 10
    ) -> list[WikidataSearchResult]:
        logging.info(f"Searching for entities with label: {label}")
        sparql_query = f"""
        SELECT ?item ?itemLabel ?itemDescription 
        (GROUP_CONCAT(DISTINCT ?alias; SEPARATOR=", ") AS ?aliases) 
        (GROUP_CONCAT(DISTINCT ?instanceOf; SEPARATOR=", ") AS ?instanceOfs) 
        (COUNT(?sitelink) AS ?sitelinkCount) WHERE {{
          ?item ?label "{label}"@en.
          ?item rdfs:label ?itemLabel.
          OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias) = "en") }}
          OPTIONAL {{ ?item wdt:P31 ?instanceOf }}
          OPTIONAL {{ ?sitelink schema:about ?item }}
          FILTER (lang(?itemLabel) = "en")
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }} GROUP BY ?item ?itemLabel ?itemDescription ORDER BY DESC(?sitelinkCount) LIMIT {limit}
        """
        url = "https://query.wikidata.org/sparql"
        headers = {"Accept": "application/sparql-results+json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params={"query": sparql_query}, headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []
                    for item in data["results"]["bindings"]:
                        result = WikidataSearchResult(
                            id=item["item"]["value"].split("/")[-1],
                            label=item["itemLabel"]["value"],
                            description=item.get("itemDescription", {}).get(
                                "value", "No description"
                            ),
                            aliases=[item["alias"]["value"]] if "alias" in item else [],
                            sitelinks=[],
                            instance_of=(
                                [item["instanceOf"]["value"].split("/")[-1]]
                                if "instanceOf" in item
                                else []
                            ),
                        )
                        results.append(result)
                    return results
                else:
                    response.raise_for_status()

    async def search_by_id(self, wikidata_id: str) -> WikidataSearchResult:
        logging.info(f"Searching for entity with ID: {wikidata_id}")
        sparql_query = f"""
        SELECT ?item ?itemLabel ?itemDescription ?instanceOf (GROUP_CONCAT(DISTINCT ?alias; SEPARATOR=", ") AS ?aliases) WHERE {{
          BIND(wd:{wikidata_id} AS ?item)
          ?item rdfs:label ?itemLabel.
          OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias) = "en") }}
          OPTIONAL {{ ?item wdt:P31 ?instanceOf }}
          FILTER (lang(?itemLabel) = "en")
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }} GROUP BY ?item ?itemLabel ?itemDescription ?instanceOf
        """
        url = "https://query.wikidata.org/sparql"
        headers = {"Accept": "application/sparql-results+json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params={"query": sparql_query}, headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    item = data["results"]["bindings"][0]
                    result = WikidataSearchResult(
                        id=item["item"]["value"].split("/")[-1],
                        label=item["itemLabel"]["value"],
                        description=item.get("itemDescription", {}).get(
                            "value", "No description"
                        ),
                        aliases=[item["alias"]["value"]] if "alias" in item else [],
                        sitelinks=[],
                        instance_of=(
                            [item["instanceOf"]["value"].split("/")[-1]]
                            if "instanceOf" in item
                            else []
                        ),
                    )
                    return result
                else:
                    response.raise_for_status()
