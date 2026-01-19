import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import get_session
from app.services.prompt_service import PromptService
from app.models import Prompt

PROMPTS = [
    {
        "prompt_type": "news_analysis",
        "system_prompt": "You are a news analyst. Extract the summary and key points according to the specialized news prompt.",
        "user_prompt": "Evaluate how the article address the title proposition ({title}). Write a short paragraph summarizing how it addresses the proposition and identify any bias in the article. This paragraph should be the 'summary'. Then, provide bullet points outlining the key points.\n\nContent: {content}",
        "description": "Specialized prompt for news articles analysis"
    },
    {
        "prompt_type": "blog_analysis",
        "system_prompt": "You are a blog editor.",
        "user_prompt": "Summarize this blog post. Identify the target audience and the main takeaway. This should be the 'summary'. Provide key sections as 'bullet_points'.\n\nContent: {content}",
        "description": "Specialized prompt for blog posts analysis"
    },
    {
        "prompt_type": "product_analysis",
        "system_prompt": "You are a technical writer.",
        "user_prompt": "Explain what the product does, its use cases and functions. This should be the 'summary'. Include examples as 'bullet_points'.\n\nContent: {content}",
        "description": "Specialized prompt for product documentation analysis"
    },
    {
        "prompt_type": "social_analysis",
        "system_prompt": "You are a social media manager.",
        "user_prompt": "Analyze this social media content. Identify the engagement strategy, key hashtags, and main message. This should be the 'summary'. Provide separate thoughts as 'bullet_points'.\n\nContent: {content}",
        "description": "Specialized prompt for social media content analysis"
    },
    {
        "prompt_type": "marketing_analysis",
        "system_prompt": "You are a marketing specialist.",
        "user_prompt": "Analyze this marketing material. Identify the value proposition, call to action, and target customer persona. This should be the 'summary'. List key features as 'bullet_points'.\n\nContent: {content}",
        "description": "Specialized prompt for marketing material analysis"
    },
    {
        "prompt_type": "book_analysis",
        "system_prompt": "You are a literary critic.",
        "user_prompt": "Provide a detailed summary of this book segment. This should be the 'summary'. Identify main themes and key chapters discussed as 'bullet_points'.\n\nContent: {content}",
        "description": "Specialized prompt for book segments analysis"
    },
    {
        "prompt_type": "generic_analysis",
        "system_prompt": "You are a content summarizer.",
        "user_prompt": "Provide a concise summary and key points for the following content.\n\nContent: {content}",
        "description": "Fallback prompt for generic content analysis"
    }
]

async def seed_prompts():
    async for session in get_session():
        prompt_service = PromptService(session)
        for p in PROMPTS:
            print(f"Seeding {p['prompt_type']}...")
            await prompt_service.create_prompt(
                prompt_type=p["prompt_type"],
                system_prompt=p["system_prompt"],
                user_prompt=p["user_prompt"],
                description=p["description"]
            )
        print("Seeding completed.")
        break

if __name__ == "__main__":
    asyncio.run(seed_prompts())
