import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)


class WikidataClient:
    def __init__(self):
        self.api_url = "https://www.wikidata.org/w/api.php"

    async def search_by_label(self, label: str, limit: int = 5) -> list[dict]:
        logging.info(f"Searching for entities with label: {label}")
        sparql_query = f"""
        SELECT ?item ?itemLabel ?itemDescription ?alias ?instanceOf WHERE {{
          ?item ?label "{label}"@en.
          ?item rdfs:label ?itemLabel.
          OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias) = "en") }}
          OPTIONAL {{ ?item wdt:P31 ?instanceOf }}
          FILTER (lang(?itemLabel) = "en")
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }} LIMIT {limit}
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
                        result = {
                            "id": item["item"]["value"].split("/")[-1],
                            "label": item["itemLabel"]["value"],
                            "description": item.get("itemDescription", {}).get(
                                "value", "No description"
                            ),
                            "alias": (
                                [item["alias"]["value"]] if "alias" in item else []
                            ),
                            "instance_of": (
                                [item["instanceOf"]["value"].split("/")[-1]]
                                if "instanceOf" in item
                                else []
                            ),
                        }
                        results.append(result)
                    return results
                else:
                    response.raise_for_status()

    async def search_by_id(self, wikidata_id: str) -> dict:
        logging.info(f"Searching for entity with ID: {wikidata_id}")
        sparql_query = f"""
        SELECT ?item ?itemLabel ?itemDescription ?alias ?instanceOf WHERE {{
          BIND(wd:{wikidata_id} AS ?item)
          ?item rdfs:label ?itemLabel.
          OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias) = "en") }}
          OPTIONAL {{ ?item wdt:P31 ?instanceOf }}
          FILTER (lang(?itemLabel) = "en")
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
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
                    result = {
                        "id": item["item"]["value"].split("/")[-1],
                        "label": item["itemLabel"]["value"],
                        "description": item.get("itemDescription", {}).get(
                            "value", "No description"
                        ),
                        "alias": ([item["alias"]["value"]] if "alias" in item else []),
                        "instance_of": (
                            [item["instanceOf"]["value"].split("/")[-1]]
                            if "instanceOf" in item
                            else []
                        ),
                    }
                    return result
                else:
                    response.raise_for_status()


async def main():
    client = WikidataClient()
    label = "BBC"
    results = await client.search_by_label(label)
    for result in results:
        print(
            f"ID: {result['id']}, Label: {result['label']}, Description: {result.get('description', 'No description')}, Also Known As: {', '.join(result['alias'])}, Instance Of: {', '.join(result['instance_of'])}"
        )
    wikidata_id = "Q43229"
    result = await client.search_by_id(wikidata_id)
    print(
        f"ID: {result['id']}, Label: {result['label']}, Description: {result.get('description', 'No description')}, Also Known As: {', '.join(result['alias'])}, Instance Of: {', '.join(result['instance_of'])}"
    )


if __name__ == "__main__":
    asyncio.run(main())
