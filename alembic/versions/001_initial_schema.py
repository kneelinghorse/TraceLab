"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2025-10-31 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgcrypto extension for gen_random_uuid support
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Projects
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('mission_protocol_id', postgresql.UUID(as_uuid=True)),
        sa.Column('research_type', sa.String()),
        sa.Column('methodology', sa.String()),
        sa.Column('status', sa.String(), server_default='active'),
        sa.Column('quality_score', sa.Integer()),
        sa.Column('last_quality_check', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint(
            "research_type IS NULL OR research_type IN ('strategic', 'tactical', 'generative', 'evaluative')",
            name='valid_research_type'
        )
    )
    
    # Documents
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('file_path', sa.String()),
        sa.Column('file_type', sa.String()),
        sa.Column('content', sa.Text()),
        sa.Column('raw_content', postgresql.BYTEA()),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('file_size', sa.BigInteger()),
        sa.Column('mime_type', sa.String()),
        sa.Column('source_type', sa.String()),
        sa.Column('participant_count', sa.Integer()),
        sa.Column('collection_date', sa.Date()),
        sa.Column('processed', sa.Boolean(), server_default='false'),
        sa.Column('chunked', sa.Boolean(), server_default='false'),
        sa.Column('embedded', sa.Boolean(), server_default='false'),
        sa.Column('transcription_accuracy', sa.Numeric(3, 2)),
        sa.Column('validation_status', sa.String(), server_default='pending'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE')
    )
    
    # Document chunks
    op.create_table(
        'document_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.String()),
        sa.Column('token_count', sa.Integer()),
        sa.Column('start_char', sa.Integer()),
        sa.Column('end_char', sa.Integer()),
        sa.Column('prev_chunk_id', postgresql.UUID(as_uuid=True)),
        sa.Column('next_chunk_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['prev_chunk_id'], ['document_chunks.id']),
        sa.ForeignKeyConstraint(['next_chunk_id'], ['document_chunks.id']),
        sa.UniqueConstraint('document_id', 'chunk_index')
    )
    
    # Tags
    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('category', sa.String()),
        sa.Column('color', sa.String()),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(['parent_id'], ['tags.id']),
        sa.UniqueConstraint('user_id', 'name', name='uq_user_tag')
    )
    
    # Document tags
    op.create_table(
        'document_tags',
        sa.Column('document_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE')
    )
    
    # Insights
    op.create_table(
        'insights',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('insight_type', sa.String()),
        sa.Column('created_by', sa.String(), server_default='human'),
        sa.Column('validated', sa.Boolean(), server_default='false'),
        sa.Column('validation_date', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE')
    )
    
    # Insight sources
    op.create_table(
        'insight_sources',
        sa.Column('insight_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('relevance_score', sa.Numeric(3, 2)),
        sa.ForeignKeyConstraint(['insight_id'], ['insights.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ondelete='CASCADE')
    )
    
    # Missions
    op.create_table(
        'missions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True)),
        sa.Column('mission_data', postgresql.JSONB(), nullable=False),
        sa.Column('quality_gates', postgresql.JSONB()),
        sa.Column('status', sa.String(), server_default='draft'),
        sa.Column('completion_percentage', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE')
    )
    
    # Quality checks
    op.create_table(
        'quality_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('check_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('details', postgresql.JSONB()),
        sa.Column('recommendations', postgresql.ARRAY(sa.String())),
        sa.Column('performed_by', sa.String()),
        sa.Column('performed_at', sa.DateTime(), server_default=sa.func.now())
    )
    
    op.create_index('idx_quality_checks_entity', 'quality_checks', ['entity_type', 'entity_id'])


def downgrade() -> None:
    op.drop_index('idx_quality_checks_entity', 'quality_checks')
    op.drop_table('quality_checks')
    op.drop_table('missions')
    op.drop_table('insight_sources')
    op.drop_table('insights')
    op.drop_table('document_tags')
    op.drop_table('tags')
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.drop_table('projects')
