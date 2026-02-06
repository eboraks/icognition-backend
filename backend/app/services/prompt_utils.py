"""
Utility functions for generating prompts for Gemini AI
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.prompt_service import PromptService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PromptType(Enum):
    """Types of prompts for different analysis tasks"""
    CONTENT_SUMMARY = "Doc Analysis: Summary"
    ENTITY_EXTRACTION = "Doc Analysis: Entities"
    TOPIC_CATEGORIZATION = "Doc Analysis: Topics"
    SENTIMENT_ANALYSIS = "Doc Analysis: Sentiment"
    LANGUAGE_DETECTION = "Doc Analysis: Language"
    CONTENT_VALIDATION = "Doc Analysis: Validation"
    BULLET_POINTS = "Doc Analysis: Bullet Points"
    OPENING_MESSAGE = "Doc Analysis: Opening Message"
    CHAT_AGENT_SYSTEM = "Chat Agent: System"
    CHAT_AGENT_TYPE_AHEAD = "Chat Agent: Type-ahead Prompt"
    CHAT_INTENT_CLASSIFICATION = "Chat Agent: Intent Classification"
    CHAT_REFLECTION = "Chat Agent: Reflection"
    EXTRACT_NEWS = "Doc Extract: News"
    EXTRACT_BLOG = "Doc Extract: Blog"
    EXTRACT_SOCIAL = "Doc Extract: Social"
    EXTRACT_PRODUCT = "Doc Extract: Product"
    EXTRACT_MARKETING = "Doc Extract: Marketing"
    EXTRACT_BOOK = "Doc Extract: Book"
    EXTRACT_GENERIC = "Doc Extract: Generic"


class PromptTemplates:
    """Templates for generating prompts for different analysis tasks"""
    
    @staticmethod
    async def _get_template_from_db(
        prompt_type: str,
        session: Optional[AsyncSession] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """Get template from database if session is available. Returns (system_prompt, user_prompt)"""
        if session:
            try:
                prompt_service = PromptService(session)
                prompt = await prompt_service.get_latest_prompt(prompt_type)
                if prompt:
                    return prompt.system_prompt, prompt.user_prompt
            except Exception as e:
                logger.warning(f"Failed to get prompt from DB for {prompt_type}: {e}")
        return None, None
    
    @staticmethod
    async def get_content_summary_prompt(
        content: str,
        max_length: int = 200,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for content summarization"""
        # Try to get template from database
        _, template = await PromptTemplates._get_template_from_db(PromptType.CONTENT_SUMMARY.value, session)
        
        # Fallback to hardcoded template
        if not template:
            template = """Please provide a concise summary of the following content in no more than {max_length} words. Focus on the main ideas and key information.

Content:
{content}

Summary:"""
        
        return template.format(content=content, max_length=max_length)

    @staticmethod
    async def get_entity_extraction_prompt(
        content: str,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for named entity extraction"""
        _, template = await PromptTemplates._get_template_from_db(PromptType.ENTITY_EXTRACTION.value, session)
        
        if not template:
            template = """Extract all named entities from the following content. Categorize them into:
- PERSON: People's names
- ORGANIZATION: Companies, institutions, groups
- LOCATION: Places, cities, countries
- EVENT: Events, conferences, meetings
- PRODUCT: Products, services, technologies
- DATE: Dates, time periods
- OTHER: Any other significant entities

Format the response as JSON with the following structure:
{{
    "entities": [
        {{
            "text": "entity text",
            "category": "PERSON|ORGANIZATION|LOCATION|EVENT|PRODUCT|DATE|OTHER",
            "confidence": 0.95,
            "context": "surrounding text for context"
        }}
    ]
}}

Content:
{content}

Entities:"""
        
        return template.format(content=content)

    @staticmethod
    async def get_topic_categorization_prompt(
        content: str,
        categories: Optional[List[str]] = None,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for topic categorization"""
        _, template = await PromptTemplates._get_template_from_db(PromptType.TOPIC_CATEGORIZATION.value, session)
        
        if not template:
            if categories:
                categories_text = ", ".join(categories)
                template = """Categorize the following content into one of these predefined categories: {categories_text}

If the content doesn't fit any of these categories, suggest a new appropriate category.

Content:
{content}

Category:"""
                return template.format(content=content, categories_text=categories_text)
            else:
                template = """Analyze the following content and identify the main topics and categories it discusses. Provide a hierarchical categorization.

Content:
{content}

Topics and Categories:"""
        
        # If template from DB has placeholders, format them
        if categories and "{categories_text}" in template:
            categories_text = ", ".join(categories)
            return template.format(content=content, categories_text=categories_text)
        
        return template.format(content=content)

    @staticmethod
    async def get_sentiment_analysis_prompt(
        content: str,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for sentiment analysis"""
        _, template = await PromptTemplates._get_template_from_db(PromptType.SENTIMENT_ANALYSIS.value, session)
        
        if not template:
            template = """Analyze the sentiment of the following content. Provide:
1. Overall sentiment (positive, negative, neutral)
2. Confidence score (0.0 to 1.0)
3. Key phrases that indicate the sentiment
4. Emotional tone (professional, casual, academic, etc.)

Format as JSON:
{{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.85,
    "key_phrases": ["phrase1", "phrase2"],
    "tone": "professional|casual|academic|technical"
}}

Content:
{content}

Sentiment Analysis:"""
        
        return template.format(content=content)

    @staticmethod
    async def get_language_detection_prompt(
        content: str,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for language detection"""
        _, template = await PromptTemplates._get_template_from_db(PromptType.LANGUAGE_DETECTION.value, session)
        
        if not template:
            template = """Identify the primary language of the following content. If multiple languages are present, identify the dominant language and list any secondary languages.

Content:
{content}

Language:"""
        
        return template.format(content=content)

    @staticmethod
    async def get_content_validation_prompt(
        content: str,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for content validation"""
        _, template = await PromptTemplates._get_template_from_db(PromptType.CONTENT_VALIDATION.value, session)
        
        if not template:
            template = """Analyze the following content and provide validation information:
1. Content quality (high, medium, low)
2. Completeness (complete, partial, incomplete)
3. Readability (excellent, good, fair, poor)
4. Potential issues or concerns
5. Content type (article, blog post, documentation, etc.)

Format as JSON:
{{
    "quality": "high|medium|low",
    "completeness": "complete|partial|incomplete",
    "readability": "excellent|good|fair|poor",
    "issues": ["issue1", "issue2"],
    "content_type": "article|blog|documentation|news|other"
}}

Content:
{content}

Validation:"""
        
        return template.format(content=content)

    @staticmethod
    async def get_bullet_points_prompt(
        content: str,
        max_points: int = 15,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Generate prompt for creating bullet points"""
        _, template = await PromptTemplates._get_template_from_db(PromptType.BULLET_POINTS.value, session)
        
        if not template:
            template = """Create {max_points} bullet points that capture the essential information from the following content. Each bullet point should be concise but informative.

Content:
{content}

Bullet Points:
•"""
        
        return template.format(content=content, max_points=max_points)

    @staticmethod
    def get_custom_prompt(content: str, instruction: str) -> str:
        """Generate a custom prompt with specific instructions"""
        return f"""{instruction}

Content:
{content}

Response:"""


class PromptBuilder:
    """Builder class for creating complex prompts"""
    
    def __init__(self):
        self.prompt_parts: List[str] = []
        self.context: Dict[str, Any] = {}
    
    def add_instruction(self, instruction: str) -> 'PromptBuilder':
        """Add an instruction to the prompt"""
        self.prompt_parts.append(instruction)
        return self
    
    def add_context(self, key: str, value: Any) -> 'PromptBuilder':
        """Add context information"""
        self.context[key] = value
        return self
    
    def add_content(self, content: str) -> 'PromptBuilder':
        """Add content to analyze"""
        self.context['content'] = content
        return self
    
    def add_format_requirements(self, format_spec: str) -> 'PromptBuilder':
        """Add format requirements"""
        self.prompt_parts.append(f"Format your response as: {format_spec}")
        return self
    
    def add_examples(self, examples: List[str]) -> 'PromptBuilder':
        """Add examples to the prompt"""
        examples_text = "\n".join(f"Example {i+1}: {ex}" for i, ex in enumerate(examples))
        self.prompt_parts.append(f"Examples:\n{examples_text}")
        return self
    
    def build(self) -> str:
        """Build the final prompt"""
        prompt = "\n\n".join(self.prompt_parts)
        
        if 'content' in self.context:
            prompt += f"\n\nContent:\n{self.context['content']}"
        
        if self.context:
            context_parts = []
            for key, value in self.context.items():
                if key != 'content':
                    context_parts.append(f"{key}: {value}")
            
            if context_parts:
                prompt += f"\n\nContext:\n" + "\n".join(context_parts)
        
        prompt += "\n\nResponse:"
        return prompt


async def generate_prompt(
    prompt_type: PromptType,
    content: str,
    session: Optional[AsyncSession] = None,
    **kwargs
) -> str:
    """
    Generate a prompt for the specified type and content
    
    Args:
        prompt_type: Type of prompt to generate
        content: Content to analyze
        session: Optional database session for fetching prompts from DB
        **kwargs: Additional parameters for the prompt
        
    Returns:
        Generated prompt string
    """
    templates = {
        PromptType.CONTENT_SUMMARY: PromptTemplates.get_content_summary_prompt,
        PromptType.ENTITY_EXTRACTION: PromptTemplates.get_entity_extraction_prompt,
        PromptType.TOPIC_CATEGORIZATION: PromptTemplates.get_topic_categorization_prompt,
        PromptType.SENTIMENT_ANALYSIS: PromptTemplates.get_sentiment_analysis_prompt,
        PromptType.LANGUAGE_DETECTION: PromptTemplates.get_language_detection_prompt,
        PromptType.CONTENT_VALIDATION: PromptTemplates.get_content_validation_prompt,
        PromptType.BULLET_POINTS: PromptTemplates.get_bullet_points_prompt,
    }
    
    if prompt_type not in templates:
        raise ValueError(f"Unsupported prompt type: {prompt_type}")
    
    return await templates[prompt_type](content, session=session, **kwargs)


def create_analysis_prompt(
    content: str,
    analysis_types: List[PromptType],
    include_metadata: bool = True
) -> str:
    """
    Create a comprehensive analysis prompt for multiple analysis types
    
    Args:
        content: Content to analyze
        analysis_types: List of analysis types to perform
        include_metadata: Whether to include metadata in the response
        
    Returns:
        Comprehensive analysis prompt
    """
    builder = PromptBuilder()
    
    builder.add_instruction("Perform a comprehensive analysis of the provided content.")
    
    analysis_instructions = []
    for analysis_type in analysis_types:
        if analysis_type == PromptType.CONTENT_SUMMARY:
            analysis_instructions.append("1. Provide a concise summary")
        elif analysis_type == PromptType.ENTITY_EXTRACTION:
            analysis_instructions.append("2. Extract named entities")
        elif analysis_type == PromptType.TOPIC_CATEGORIZATION:
            analysis_instructions.append("3. Categorize topics")
        elif analysis_type == PromptType.SENTIMENT_ANALYSIS:
            analysis_instructions.append("4. Analyze sentiment")
        elif analysis_type == PromptType.LANGUAGE_DETECTION:
            analysis_instructions.append("5. Detect language")
        elif analysis_type == PromptType.CONTENT_VALIDATION:
            analysis_instructions.append("6. Validate content quality")
        elif analysis_type == PromptType.BULLET_POINTS:
            analysis_instructions.append("7. Create bullet points")
    
    builder.add_instruction("\n".join(analysis_instructions))
    
    if include_metadata:
        builder.add_format_requirements("""
{
    "summary": "concise summary",
    "bullet_points": ["• point1", "• point2"],
    "entities": [
        {
            "text": "entity",
            "category": "PERSON|ORGANIZATION|etc",
            "confidence": 0.95
        }
    ],
    "topics": ["topic1", "topic2"],
    "sentiment": {
        "overall": "positive|negative|neutral",
        "confidence": 0.85
    },
    "language": "primary language",
    "quality": "high|medium|low",
    "bullet_points": ["• point1", "• point2"],
    "metadata": {
        "word_count": 150,
        "analysis_timestamp": "2024-01-01T00:00:00Z"
    }
}""")
    
    builder.add_content(content)
    
    return builder.build()
