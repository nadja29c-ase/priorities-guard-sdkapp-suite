"""convert_scope_to_array_and_fix_refresh_token_expires

Revision ID: 079b2ef29616
Revises: 2ab26a1bd81b
Create Date: 2025-11-22 10:04:30.950558

Schema improvements:
1. Convert scope from String to ARRAY(String) in oauth_authorization_codes
2. Convert scope from String to ARRAY(String) in oauth_access_tokens
3. Make refresh_token_expires_at NOT NULL in oauth_access_tokens

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '079b2ef29616'
down_revision: Union[str, Sequence[str], None] = '2ab26a1bd81b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Convert scope to ARRAY in oauth_authorization_codes
    # Add new array column
    op.add_column('oauth_authorization_codes',
        sa.Column('scope_array', postgresql.ARRAY(sa.String()), nullable=True))

    # Migrate data: split space-separated string into array
    op.execute("""
        UPDATE oauth_authorization_codes
        SET scope_array = string_to_array(scope, ' ')
    """)

    # Drop old column and rename new one
    op.drop_column('oauth_authorization_codes', 'scope')
    op.alter_column('oauth_authorization_codes', 'scope_array', new_column_name='scope')
    op.alter_column('oauth_authorization_codes', 'scope', nullable=False)

    # 2. Convert scope to ARRAY in oauth_access_tokens
    # Add new array column
    op.add_column('oauth_access_tokens',
        sa.Column('scope_array', postgresql.ARRAY(sa.String()), nullable=True))

    # Migrate data: split space-separated string into array
    op.execute("""
        UPDATE oauth_access_tokens
        SET scope_array = string_to_array(scope, ' ')
    """)

    # Drop old column and rename new one
    op.drop_column('oauth_access_tokens', 'scope')
    op.alter_column('oauth_access_tokens', 'scope_array', new_column_name='scope')
    op.alter_column('oauth_access_tokens', 'scope', nullable=False)

    # 3. Make refresh_token_expires_at NOT NULL
    # First set a default value for existing NULL rows (should not exist but just in case)
    op.execute("""
        UPDATE oauth_access_tokens
        SET refresh_token_expires_at = created_at + INTERVAL '30 days'
        WHERE refresh_token_expires_at IS NULL
    """)

    # Then make column NOT NULL
    op.alter_column('oauth_access_tokens', 'refresh_token_expires_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    # 1. Make refresh_token_expires_at nullable again
    op.alter_column('oauth_access_tokens', 'refresh_token_expires_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True)

    # 2. Convert scope back to String in oauth_access_tokens
    op.add_column('oauth_access_tokens',
        sa.Column('scope_string', sa.String(length=512), nullable=True))

    # Migrate data: join array back to space-separated string
    op.execute("""
        UPDATE oauth_access_tokens
        SET scope_string = array_to_string(scope, ' ')
    """)

    op.drop_column('oauth_access_tokens', 'scope')
    op.alter_column('oauth_access_tokens', 'scope_string', new_column_name='scope')
    op.alter_column('oauth_access_tokens', 'scope', nullable=False)

    # 3. Convert scope back to String in oauth_authorization_codes
    op.add_column('oauth_authorization_codes',
        sa.Column('scope_string', sa.String(length=512), nullable=True))

    # Migrate data: join array back to space-separated string
    op.execute("""
        UPDATE oauth_authorization_codes
        SET scope_string = array_to_string(scope, ' ')
    """)

    op.drop_column('oauth_authorization_codes', 'scope')
    op.alter_column('oauth_authorization_codes', 'scope_string', new_column_name='scope')
    op.alter_column('oauth_authorization_codes', 'scope', nullable=False)
