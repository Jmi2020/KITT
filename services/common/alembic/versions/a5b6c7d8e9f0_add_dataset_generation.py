"""add_dataset_generation

Revision ID: a5b6c7d8e9f0
Revises: 4e5f6a7b8c9d
Create Date: 2025-01-02

Autonomous Dataset Generation & Fine-Tuning System:
- research_topics: Topic tracking with maturation scores
- research_papers: Harvested paper storage with source IDs
- paper_topics: Junction table for paper-topic relationships
- extracted_claims: Classified claims with evidence and embeddings
- dataset_entries: Alpaca-format training data
- training_batches: Batch export tracking
- expert_models: Fine-tuned model registry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, ENUM


# revision identifiers, used by Alembic.
revision = 'a5b6c7d8e9f0'
down_revision = '4e5f6a7b8c9d'
branch_labels = None
depends_on = None


def upgrade():
    """Apply dataset generation schema changes."""

    # Create new enum types
    topic_status_enum = ENUM(
        'pending', 'harvesting', 'extracting', 'evaluating',
        'mature', 'finetuning', 'completed', 'paused',
        name='topicstatus'
    )
    topic_status_enum.create(op.get_bind(), checkfirst=True)

    claim_type_enum = ENUM(
        'finding', 'method', 'definition', 'comparison', 'limitation',
        name='claimtype'
    )
    claim_type_enum.create(op.get_bind(), checkfirst=True)

    section_type_enum = ENUM(
        'abstract', 'introduction', 'methods', 'results',
        'discussion', 'conclusion', 'unknown',
        name='sectiontype'
    )
    section_type_enum.create(op.get_bind(), checkfirst=True)

    entry_status_enum = ENUM(
        'pending', 'accepted', 'refined', 'rejected',
        name='entrystatus'
    )
    entry_status_enum.create(op.get_bind(), checkfirst=True)

    batch_status_enum = ENUM(
        'pending', 'generating', 'completed', 'failed',
        name='batchstatus'
    )
    batch_status_enum.create(op.get_bind(), checkfirst=True)

    # Create research_topics table
    op.create_table(
        'research_topics',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('description', sa.Text),
        sa.Column('query_terms', ARRAY(sa.String), nullable=False),
        sa.Column('categories', ARRAY(sa.String), server_default='{}'),
        sa.Column('sources', ARRAY(sa.String), server_default='{"arxiv"}'),

        # Configuration
        sa.Column('target_papers', sa.Integer, server_default='500'),
        sa.Column('target_entries', sa.Integer, server_default='5000'),
        sa.Column('min_citations', sa.Integer, server_default='0'),
        sa.Column('date_from', sa.DateTime),
        sa.Column('date_to', sa.DateTime),
        sa.Column('auto_finetune', sa.Boolean, server_default='false'),

        # Status and progress
        sa.Column('status', ENUM(name='topicstatus', create_type=False),
                  server_default='pending'),
        sa.Column('papers_harvested', sa.Integer, server_default='0'),
        sa.Column('papers_processed', sa.Integer, server_default='0'),
        sa.Column('claims_extracted', sa.Integer, server_default='0'),
        sa.Column('claims_accepted', sa.Integer, server_default='0'),
        sa.Column('dataset_entries', sa.Integer, server_default='0'),

        # Maturation metrics
        sa.Column('maturation_score', sa.Numeric(5, 4), server_default='0.0'),
        sa.Column('topic_coverage_score', sa.Numeric(5, 4), server_default='0.0'),
        sa.Column('claim_conflict_rate', sa.Numeric(5, 4), server_default='0.0'),

        # Configuration and metadata
        sa.Column('config', JSONB, server_default='{}'),
        sa.Column('topic_metadata', JSONB, server_default='{}'),

        # Timestamps
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_harvest_at', sa.DateTime),
        sa.Column('last_evaluation_at', sa.DateTime),
    )

    # Create research_papers table
    op.create_table(
        'research_papers',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),

        # Source IDs (at least one required)
        sa.Column('arxiv_id', sa.String(50)),
        sa.Column('semantic_scholar_id', sa.String(100)),
        sa.Column('pubmed_id', sa.String(50)),
        sa.Column('core_id', sa.String(100)),
        sa.Column('doi', sa.String(255)),

        # Content
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('abstract', sa.Text),
        sa.Column('full_text', sa.Text),
        sa.Column('authors', JSONB, server_default='[]'),
        sa.Column('published_date', sa.DateTime),
        sa.Column('citations_count', sa.Integer, server_default='0'),

        # Source and storage
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('source_url', sa.String(500)),
        sa.Column('pdf_url', sa.String(500)),
        sa.Column('pdf_path', sa.String(500)),

        # Processing status
        sa.Column('text_extracted', sa.Boolean, server_default='false'),
        sa.Column('claims_extracted', sa.Boolean, server_default='false'),
        sa.Column('embedding_id', sa.String(100)),

        # Timestamps
        sa.Column('harvested_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('processed_at', sa.DateTime),
    )

    # Create unique indexes for source IDs (allow NULL but enforce uniqueness when present)
    op.create_index('idx_papers_arxiv_id', 'research_papers', ['arxiv_id'],
                    unique=True, postgresql_where=sa.text('arxiv_id IS NOT NULL'))
    op.create_index('idx_papers_s2_id', 'research_papers', ['semantic_scholar_id'],
                    unique=True, postgresql_where=sa.text('semantic_scholar_id IS NOT NULL'))
    op.create_index('idx_papers_pubmed_id', 'research_papers', ['pubmed_id'],
                    unique=True, postgresql_where=sa.text('pubmed_id IS NOT NULL'))
    op.create_index('idx_papers_core_id', 'research_papers', ['core_id'],
                    unique=True, postgresql_where=sa.text('core_id IS NOT NULL'))

    # Create paper_topics junction table
    op.create_table(
        'paper_topics',
        sa.Column('paper_id', UUID(as_uuid=False),
                  sa.ForeignKey('research_papers.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('topic_id', UUID(as_uuid=False),
                  sa.ForeignKey('research_topics.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('added_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create extracted_claims table
    op.create_table(
        'extracted_claims',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('paper_id', UUID(as_uuid=False),
                  sa.ForeignKey('research_papers.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('session_id', sa.String(100)),

        # Claim content
        sa.Column('claim_text', sa.Text, nullable=False),
        sa.Column('claim_type', ENUM(name='claimtype', create_type=False), nullable=False),
        sa.Column('section', ENUM(name='sectiontype', create_type=False),
                  server_default='unknown'),

        # Evidence
        sa.Column('evidence_quotes', JSONB, nullable=False),
        sa.Column('evidence_positions', JSONB, server_default='[]'),
        sa.Column('citations', JSONB, server_default='[]'),

        # Scores
        sa.Column('confidence', sa.Numeric(5, 4), server_default='0.0'),
        sa.Column('provenance_score', sa.Numeric(5, 4), server_default='0.0'),
        sa.Column('entailment_score', sa.Numeric(5, 4), server_default='0.0'),
        sa.Column('novelty_score', sa.Numeric(5, 4), server_default='0.0'),

        # Embedding and deduplication
        sa.Column('embedding_id', sa.String(100)),
        sa.Column('dedupe_fingerprint', sa.String(32)),

        # Evaluation
        sa.Column('evaluation_status', ENUM(name='entrystatus', create_type=False),
                  server_default='pending'),
        sa.Column('evaluation_notes', sa.Text),

        # Timestamps
        sa.Column('extracted_at', sa.DateTime,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('evaluated_at', sa.DateTime),
    )

    # Create dataset_entries table
    op.create_table(
        'dataset_entries',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('topic_id', UUID(as_uuid=False),
                  sa.ForeignKey('research_topics.id', ondelete='CASCADE'),
                  nullable=False),

        # Alpaca format fields
        sa.Column('instruction', sa.Text, nullable=False),
        sa.Column('input', sa.Text, server_default=''),
        sa.Column('output', sa.Text, nullable=False),

        # Provenance
        sa.Column('source_paper_ids', JSONB, nullable=False),
        sa.Column('source_claim_ids', JSONB, nullable=False),

        # Quality
        sa.Column('quality_score', sa.Numeric(5, 4), server_default='0.0'),
        sa.Column('evaluation_status', ENUM(name='entrystatus', create_type=False),
                  server_default='pending'),
        sa.Column('evaluation_notes', sa.Text),

        # Batch tracking
        sa.Column('batch_id', UUID(as_uuid=False)),

        # Timestamps
        sa.Column('generated_at', sa.DateTime,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('evaluated_at', sa.DateTime),
    )

    # Create training_batches table
    op.create_table(
        'training_batches',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('topic_id', UUID(as_uuid=False),
                  sa.ForeignKey('research_topics.id', ondelete='CASCADE'),
                  nullable=False),

        # Batch info
        sa.Column('batch_number', sa.Integer, nullable=False),
        sa.Column('entry_count', sa.Integer, nullable=False),
        sa.Column('file_path', sa.String(500)),
        sa.Column('file_format', sa.String(20), server_default='alpaca_json'),
        sa.Column('file_size_bytes', sa.BigInteger),

        # Status
        sa.Column('status', ENUM(name='batchstatus', create_type=False),
                  server_default='pending'),
        sa.Column('error_message', sa.Text),

        # Quality metrics
        sa.Column('avg_quality_score', sa.Numeric(5, 4)),
        sa.Column('accepted_count', sa.Integer),
        sa.Column('rejected_count', sa.Integer),

        # Timestamps
        sa.Column('created_at', sa.DateTime,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime),
    )

    # Create expert_models table
    op.create_table(
        'expert_models',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('model_id', sa.String(100), nullable=False, unique=True),
        sa.Column('topic_id', UUID(as_uuid=False),
                  sa.ForeignKey('research_topics.id', ondelete='SET NULL')),
        sa.Column('topic_name', sa.String(255), nullable=False),

        # Model info
        sa.Column('base_model', sa.String(255), nullable=False),
        sa.Column('adapter_path', sa.String(500)),
        sa.Column('gguf_path', sa.String(500)),

        # Training info
        sa.Column('training_samples', sa.Integer, nullable=False),
        sa.Column('training_epochs', sa.Integer, nullable=False),
        sa.Column('training_loss', sa.Numeric(8, 6)),
        sa.Column('validation_loss', sa.Numeric(8, 6)),

        # Training config
        sa.Column('training_config', JSONB, server_default='{}'),
        sa.Column('metrics', JSONB, server_default='{}'),

        # Status
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('registered_in_kitt', sa.Boolean, server_default='false'),

        # Timestamps
        sa.Column('created_at', sa.DateTime,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create indexes for performance
    # research_topics indexes
    op.create_index('idx_topics_status', 'research_topics', ['status'],
                    postgresql_using='btree')
    op.create_index('idx_topics_maturation', 'research_topics', ['maturation_score'],
                    postgresql_using='btree')

    # research_papers indexes
    op.create_index('idx_papers_source', 'research_papers', ['source'],
                    postgresql_using='btree')
    op.create_index('idx_papers_doi', 'research_papers', ['doi'],
                    postgresql_using='btree')
    op.create_index('idx_papers_harvested_at', 'research_papers', ['harvested_at'],
                    postgresql_using='btree')

    # paper_topics indexes
    op.create_index('idx_paper_topics_topic', 'paper_topics', ['topic_id'],
                    postgresql_using='btree')

    # extracted_claims indexes
    op.create_index('idx_claims_paper_id', 'extracted_claims', ['paper_id'],
                    postgresql_using='btree')
    op.create_index('idx_claims_type', 'extracted_claims', ['claim_type'],
                    postgresql_using='btree')
    op.create_index('idx_claims_fingerprint', 'extracted_claims', ['dedupe_fingerprint'],
                    postgresql_using='btree')
    op.create_index('idx_claims_eval_status', 'extracted_claims', ['evaluation_status'],
                    postgresql_using='btree')

    # dataset_entries indexes
    op.create_index('idx_entries_topic_id', 'dataset_entries', ['topic_id'],
                    postgresql_using='btree')
    op.create_index('idx_entries_status', 'dataset_entries', ['evaluation_status'],
                    postgresql_using='btree')
    op.create_index('idx_entries_quality', 'dataset_entries', ['quality_score'],
                    postgresql_using='btree')
    op.create_index('idx_entries_batch_id', 'dataset_entries', ['batch_id'],
                    postgresql_using='btree')

    # training_batches indexes
    op.create_index('idx_batches_topic_id', 'training_batches', ['topic_id'],
                    postgresql_using='btree')
    op.create_index('idx_batches_status', 'training_batches', ['status'],
                    postgresql_using='btree')

    # expert_models indexes
    op.create_index('idx_experts_topic_id', 'expert_models', ['topic_id'],
                    postgresql_using='btree')
    op.create_index('idx_experts_active', 'expert_models', ['is_active'],
                    postgresql_using='btree',
                    postgresql_where=sa.text('is_active = true'))


def downgrade():
    """Rollback dataset generation schema changes."""

    # Drop indexes
    op.drop_index('idx_experts_active', table_name='expert_models')
    op.drop_index('idx_experts_topic_id', table_name='expert_models')
    op.drop_index('idx_batches_status', table_name='training_batches')
    op.drop_index('idx_batches_topic_id', table_name='training_batches')
    op.drop_index('idx_entries_batch_id', table_name='dataset_entries')
    op.drop_index('idx_entries_quality', table_name='dataset_entries')
    op.drop_index('idx_entries_status', table_name='dataset_entries')
    op.drop_index('idx_entries_topic_id', table_name='dataset_entries')
    op.drop_index('idx_claims_eval_status', table_name='extracted_claims')
    op.drop_index('idx_claims_fingerprint', table_name='extracted_claims')
    op.drop_index('idx_claims_type', table_name='extracted_claims')
    op.drop_index('idx_claims_paper_id', table_name='extracted_claims')
    op.drop_index('idx_paper_topics_topic', table_name='paper_topics')
    op.drop_index('idx_papers_harvested_at', table_name='research_papers')
    op.drop_index('idx_papers_doi', table_name='research_papers')
    op.drop_index('idx_papers_source', table_name='research_papers')
    op.drop_index('idx_papers_core_id', table_name='research_papers')
    op.drop_index('idx_papers_pubmed_id', table_name='research_papers')
    op.drop_index('idx_papers_s2_id', table_name='research_papers')
    op.drop_index('idx_papers_arxiv_id', table_name='research_papers')
    op.drop_index('idx_topics_maturation', table_name='research_topics')
    op.drop_index('idx_topics_status', table_name='research_topics')

    # Drop tables (in reverse order of dependencies)
    op.drop_table('expert_models')
    op.drop_table('training_batches')
    op.drop_table('dataset_entries')
    op.drop_table('extracted_claims')
    op.drop_table('paper_topics')
    op.drop_table('research_papers')
    op.drop_table('research_topics')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS batchstatus")
    op.execute("DROP TYPE IF EXISTS entrystatus")
    op.execute("DROP TYPE IF EXISTS sectiontype")
    op.execute("DROP TYPE IF EXISTS claimtype")
    op.execute("DROP TYPE IF EXISTS topicstatus")
