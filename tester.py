from app.wikidata_client import WikidataClient
import app.entity_handler as entity_handler
import asyncio


async def wikidata_search():
    client = WikidataClient()
    label = "Rousseau"
    results = await client.search_by_label(label)
    for result in results:
        print(result.model_dump_json())
    print("--------------------------------------------------")
    results = await client.text_search(label)
    for result in results:
        print(result.model_dump_json())


async def main():
    await entity_handler.merge_duplicate_entities()


if __name__ == "__main__":
    asyncio.run(main())
