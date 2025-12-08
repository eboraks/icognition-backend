"""add user role and prompts

Revision ID: 005858a876b8
Revises: 4084848d3cc8
Create Date: 2025-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005858a876b8'
down_revision: Union[str, Sequence[str], None] = '4084848d3cc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add role column to users table
    op.add_column('users', sa.Column('role', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    op.create_index('ix_users_role', 'users', ['role'], unique=False)
    
    # Create prompts table
    op.create_table('prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prompt_type', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_prompts_prompt_type', 'prompts', ['prompt_type'], unique=False)
    op.create_index('ix_prompts_is_active', 'prompts', ['is_active'], unique=False)
    op.create_index('ix_prompts_type_version', 'prompts', ['prompt_type', 'version'], unique=True)
    op.create_index('ix_prompts_type_active', 'prompts', ['prompt_type', 'is_active'], unique=False)
    
    # Seed initial prompts from existing code
    # This will be done in a data migration function
    seed_initial_prompts()


def seed_initial_prompts() -> None:
    """Seed initial prompts from existing codebase"""
    from sqlalchemy import text
    
    # Get a connection to insert data
    connection = op.get_bind()
    
    # Find first sysadmin user or use a system user ID
    try:
        result = connection.execute(text("SELECT id FROM users WHERE role = 'sysadmin' LIMIT 1"))
        sysadmin_user = result.fetchone()
        created_by = sysadmin_user[0] if sysadmin_user else None
    except Exception:
        created_by = None
    
    # If no sysadmin exists, try to get any user or use a placeholder
    if not created_by:
        try:
            result = connection.execute(text("SELECT id FROM users LIMIT 1"))
            user = result.fetchone()
            created_by = user[0] if user else None
        except Exception:
            created_by = None
    
    # If still no user, use NULL (will be set to NULL in DB)
    if not created_by:
        created_by = None
    
    # ReAct agent system prompt (from chat_agent_service.py lines 229-238)
    react_agent_system_prompt = (
        "You are a helpful research assistant that can answer questions using the user's document library. "
        "When users ask questions, use the retrieve_documents_tool to find relevant documents from their library. "
        "IMPORTANT: After retrieving documents, you must synthesize the information and provide a comprehensive, "
        "natural-language answer to the user's question. Do NOT simply repeat the tool output verbatim. "
        "Use the retrieved document content to craft a clear, well-structured response that directly answers "
        "the user's question. If the documents don't contain relevant information, let the user know clearly. "
        "The tool returns cleaned text content - use it to inform your answer. Always cite document titles and URLs "
        "when referencing specific documents."
    )
    
    # REACT_PROMPT template (from prompts.py)
    react_agent_template = """Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
    
    # Prompt templates extracted from PromptTemplates class
    # These are the base templates without content substitution
    prompt_templates = [
        ('content_summary', 'Please provide a concise summary of the following content in no more than {max_length} words. Focus on the main ideas and key information.\n\nContent:\n{content}\n\nSummary:', 'Initial version of content_summary prompt'),
        ('key_points', 'Extract the {max_points} most important key points from the following content. Present each point as a clear, concise statement.\n\nContent:\n{content}\n\nKey Points:\n1.', 'Initial version of key_points prompt'),
        ('entity_extraction', 'Extract all named entities from the following content. Categorize them into:\n- PERSON: People\'s names\n- ORGANIZATION: Companies, institutions, groups\n- LOCATION: Places, cities, countries\n- EVENT: Events, conferences, meetings\n- PRODUCT: Products, services, technologies\n- DATE: Dates, time periods\n- OTHER: Any other significant entities\n\nFormat the response as JSON with the following structure:\n{{\n    "entities": [\n        {{\n            "text": "entity text",\n            "category": "PERSON|ORGANIZATION|LOCATION|EVENT|PRODUCT|DATE|OTHER",\n            "confidence": 0.95,\n            "context": "surrounding text for context"\n        }}\n    ]\n}}\n\nContent:\n{content}\n\nEntities:', 'Initial version of entity_extraction prompt'),
        ('topic_categorization', 'Analyze the following content and identify the main topics and categories it discusses. Provide a hierarchical categorization.\n\nContent:\n{content}\n\nTopics and Categories:', 'Initial version of topic_categorization prompt'),
        ('sentiment_analysis', 'Analyze the sentiment of the following content. Provide:\n1. Overall sentiment (positive, negative, neutral)\n2. Confidence score (0.0 to 1.0)\n3. Key phrases that indicate the sentiment\n4. Emotional tone (professional, casual, academic, etc.)\n\nFormat as JSON:\n{{\n    "sentiment": "positive|negative|neutral",\n    "confidence": 0.85,\n    "key_phrases": ["phrase1", "phrase2"],\n    "tone": "professional|casual|academic|technical"\n}}\n\nContent:\n{content}\n\nSentiment Analysis:', 'Initial version of sentiment_analysis prompt'),
        ('language_detection', 'Identify the primary language of the following content. If multiple languages are present, identify the dominant language and list any secondary languages.\n\nContent:\n{content}\n\nLanguage:', 'Initial version of language_detection prompt'),
        ('content_validation', 'Analyze the following content and provide validation information:\n1. Content quality (high, medium, low)\n2. Completeness (complete, partial, incomplete)\n3. Readability (excellent, good, fair, poor)\n4. Potential issues or concerns\n5. Content type (article, blog post, documentation, etc.)\n\nFormat as JSON:\n{{\n    "quality": "high|medium|low",\n    "completeness": "complete|partial|incomplete",\n    "readability": "excellent|good|fair|poor",\n    "issues": ["issue1", "issue2"],\n    "content_type": "article|blog|documentation|news|other"\n}}\n\nContent:\n{content}\n\nValidation:', 'Initial version of content_validation prompt'),
        ('bullet_points', 'Create {max_points} bullet points that capture the essential information from the following content. Each bullet point should be concise but informative.\n\nContent:\n{content}\n\nBullet Points:\n•', 'Initial version of bullet_points prompt'),
    ]
    
    # Insert all prompt templates
    for prompt_type, content, description in prompt_templates:
        connection.execute(
            text("""
                INSERT INTO prompts (prompt_type, version, content, description, is_active, created_by, created_at, updated_at)
                VALUES (:prompt_type, 1, :content, :description, true, :created_by, now(), now())
            """),
            {
                'prompt_type': prompt_type,
                'content': content,
                'description': description,
                'created_by': created_by
            }
        )
    
    # Insert ReAct agent system prompt
    connection.execute(
        text("""
            INSERT INTO prompts (prompt_type, version, content, description, is_active, created_by, created_at, updated_at)
            VALUES ('react_agent_system', 1, :content, :description, true, :created_by, now(), now())
        """),
        {
            'content': react_agent_system_prompt,
            'description': 'Initial system prompt for ReAct chat agent',
            'created_by': created_by
        }
    )
    
    # Insert REACT_PROMPT template
    connection.execute(
        text("""
            INSERT INTO prompts (prompt_type, version, content, description, is_active, created_by, created_at, updated_at)
            VALUES ('react_agent_template', 1, :content, :description, true, :created_by, now(), now())
        """),
        {
            'content': react_agent_template,
            'description': 'ReAct agent template with placeholders',
            'created_by': created_by
        }
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_prompts_type_active', table_name='prompts')
    op.drop_index('ix_prompts_type_version', table_name='prompts')
    op.drop_index('ix_prompts_is_active', table_name='prompts')
    op.drop_index('ix_prompts_prompt_type', table_name='prompts')
    op.drop_table('prompts')
    op.drop_index('ix_users_role', table_name='users')
    op.drop_column('users', 'role')

