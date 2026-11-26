"""Add nullable profile fields (age, designation, hospital_name, avatar_data_url) to users.

Revision ID: 0002_user_profile_fields
Revises: 0001_initial_schema
Create Date: 2026-11-26 10:25:00+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_user_profile_fields"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("designation", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("hospital_name", sa.String(length=160), nullable=True))
    op.add_column("users", sa.Column("avatar_data_url", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_users_age_range",
        "users",
        "age IS NULL OR (age >= 18 AND age <= 120)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_age_range", "users", type_="check")
    op.drop_column("users", "avatar_data_url")
    op.drop_column("users", "hospital_name")
    op.drop_column("users", "designation")
    op.drop_column("users", "age")
