from typing import Sequence, Union

from alembic import op

revision: str = "ff920c1ee1f9"
down_revision: Union[str, Sequence[str], None] = "34284b4e7eaf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app_user ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE app_user ADD COLUMN IF NOT EXISTS verify_code_hash VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE app_user ADD COLUMN IF NOT EXISTS verify_code_expires_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.drop_column("app_user", "verify_code_expires_at")
    op.drop_column("app_user", "verify_code_hash")
    op.drop_column("app_user", "email_verified_at")