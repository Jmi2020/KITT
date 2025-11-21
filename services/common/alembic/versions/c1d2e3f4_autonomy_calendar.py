"""Add autonomy calendar scheduling tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c1d2e3f4_autonomy_calendar"
down_revision = "k1l2m3n4o5p6_add_apscheduler_job_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autonomous_schedules",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("job_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("natural_language_schedule", sa.Text(), nullable=True),
        sa.Column("cron_expression", sa.String(length=100), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("budget_limit_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_execution_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_execution_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_autonomous_user_enabled", "autonomous_schedules", ["user_id", "enabled"])
    op.create_index("idx_autonomous_next_execution", "autonomous_schedules", ["next_execution_at"])

    op.create_table(
        "job_execution_history",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("job_name", sa.String(length=255), nullable=False),
        sa.Column("execution_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("budget_spent_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_job_execution_time", "job_execution_history", ["job_id", "execution_time"])
    op.create_index("idx_job_execution_status", "job_execution_history", ["status"])

    op.create_table(
        "budget_forecasts",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("total_scheduled_jobs", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("actual_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("daily_limit_usd", sa.Numeric(10, 4), nullable=False, server_default="5.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("forecast_date", name="uq_budget_forecast_date"),
    )


def downgrade() -> None:
    op.drop_table("budget_forecasts")
    op.drop_index("idx_job_execution_status", table_name="job_execution_history")
    op.drop_index("idx_job_execution_time", table_name="job_execution_history")
    op.drop_table("job_execution_history")
    op.drop_index("idx_autonomous_next_execution", table_name="autonomous_schedules")
    op.drop_index("idx_autonomous_user_enabled", table_name="autonomous_schedules")
    op.drop_table("autonomous_schedules")
