from app.wikidata_client import WikidataClient
import asyncio


async def main():
    client = WikidataClient()
    label = "Rousseau"
    results = await client.search_by_label(label)
    for result in results:
        print(result.model_dump_json())
    print("--------------------------------------------------")
    results = await client.text_search(label)
    for result in results:
        print(result.model_dump_json())


if __name__ == "__main__":
    asyncio.run(main())
