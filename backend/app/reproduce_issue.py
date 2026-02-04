
import asyncio
import sys
import os

# Add the project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.services.web_fetcher import WebPageFetcher

async def reproduce():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Subscriptions | Substack</title>
        <meta name="description" content="A newsletter platform">
        <meta property="og:title" content="Why Israel Is Seen Everywhere and Everything Else is Forgotten" />
        <meta property="og:description" content="A deep dive into media coverage..." />
        <meta property="og:image" content="https://example.com/image.jpg" />
        <meta name="twitter:image" content="https://example.com/twitter_image.jpg" />
    </head>
    <body>
        <h1>Subscriptions | Substack</h1>
        <p>Some content here.</p>
    </body>
    </html>
    """

    fetcher = WebPageFetcher()
    metadata = fetcher.extract_enhanced_metadata(html_content)
    
    print("--- Extracted Metadata ---")
    print(f"Title: {metadata.get('title')}")
    print(f"Description: {metadata.get('description')}")
    print(f"Image: {metadata.get('image') or metadata.get('image_url')}")
    
    # Verification logic
    # Current buggy behavior: Title is "Subscriptions | Substack"
    # Desired behavior: Title is "Why Israel Is Seen Everywhere..."
    
    if metadata.get('title') == "Subscriptions | Substack":
        print("\n[CONFIRMED] Issue reproduced: Title comes from <title> tag instead of og:title.")
    else:
        print(f"\n[UNEXPECTED] Title is: {metadata.get('title')}")
        
    if metadata.get('description') == "A newsletter platform":
        print("[CONFIRMED] Issue reproduced: Description comes from <meta name='description'> instead of og:description.")
    
    if not (metadata.get('image') or metadata.get('image_url')):
        print("[CONFIRMED] Issue reproduced: Image URL is missing.")

if __name__ == "__main__":
    asyncio.run(reproduce())
