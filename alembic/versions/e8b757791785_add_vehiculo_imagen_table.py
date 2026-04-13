"""add vehiculo_imagen table

Revision ID: e8b757791785
Revises: d7a646680674
Create Date: 2026-04-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b757791785'
down_revision: Union[str, None] = 'd7a646680674'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crear tabla vehiculos_imagenes
    op.create_table(
        'vehiculos_imagenes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vehiculo_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_url', sa.String(length=500), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('es_principal', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('descripcion', sa.String(length=255), nullable=True),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Crear índices
    op.create_index(
        op.f('ix_vehiculos_imagenes_vehiculo_id'),
        'vehiculos_imagenes',
        ['vehiculo_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_vehiculos_imagenes_uploaded_by'),
        'vehiculos_imagenes',
        ['uploaded_by'],
        unique=False
    )
    
    # Crear foreign keys
    op.create_foreign_key(
        'fk_vehiculos_imagenes_vehiculo_id',
        'vehiculos_imagenes',
        'vehiculos',
        ['vehiculo_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_vehiculos_imagenes_uploaded_by',
        'vehiculos_imagenes',
        'users',
        ['uploaded_by'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Actualizar tabla evidencias_imagenes (agregar campos faltantes)
    op.add_column('evidencias_imagenes', sa.Column('file_name', sa.String(length=255), nullable=True))
    op.add_column('evidencias_imagenes', sa.Column('file_type', sa.String(length=50), nullable=True))
    op.add_column('evidencias_imagenes', sa.Column('mime_type', sa.String(length=100), nullable=True))
    op.add_column('evidencias_imagenes', sa.Column('size', sa.Integer(), nullable=True))
    op.add_column('evidencias_imagenes', sa.Column('uploaded_by', sa.Integer(), nullable=True))
    op.add_column('evidencias_imagenes', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    
    # Renombrar columna imagen_url a file_url
    op.alter_column('evidencias_imagenes', 'imagen_url', new_column_name='file_url')
    
    # Crear índice y foreign key para uploaded_by
    op.create_index(
        op.f('ix_evidencias_imagenes_uploaded_by'),
        'evidencias_imagenes',
        ['uploaded_by'],
        unique=False
    )
    op.create_foreign_key(
        'fk_evidencias_imagenes_uploaded_by',
        'evidencias_imagenes',
        'users',
        ['uploaded_by'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Actualizar tabla evidencias_audios (agregar campos faltantes)
    op.add_column('evidencias_audios', sa.Column('file_name', sa.String(length=255), nullable=True))
    op.add_column('evidencias_audios', sa.Column('file_type', sa.String(length=50), nullable=True))
    op.add_column('evidencias_audios', sa.Column('mime_type', sa.String(length=100), nullable=True))
    op.add_column('evidencias_audios', sa.Column('size', sa.Integer(), nullable=True))
    op.add_column('evidencias_audios', sa.Column('duration', sa.Integer(), nullable=True))
    op.add_column('evidencias_audios', sa.Column('uploaded_by', sa.Integer(), nullable=True))
    op.add_column('evidencias_audios', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    
    # Renombrar columna audio_url a file_url
    op.alter_column('evidencias_audios', 'audio_url', new_column_name='file_url')
    
    # Crear índice y foreign key para uploaded_by
    op.create_index(
        op.f('ix_evidencias_audios_uploaded_by'),
        'evidencias_audios',
        ['uploaded_by'],
        unique=False
    )
    op.create_foreign_key(
        'fk_evidencias_audios_uploaded_by',
        'evidencias_audios',
        'users',
        ['uploaded_by'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Eliminar foreign keys y índices de evidencias_audios
    op.drop_constraint('fk_evidencias_audios_uploaded_by', 'evidencias_audios', type_='foreignkey')
    op.drop_index(op.f('ix_evidencias_audios_uploaded_by'), table_name='evidencias_audios')
    
    # Renombrar columna file_url a audio_url
    op.alter_column('evidencias_audios', 'file_url', new_column_name='audio_url')
    
    # Eliminar columnas agregadas
    op.drop_column('evidencias_audios', 'created_at')
    op.drop_column('evidencias_audios', 'uploaded_by')
    op.drop_column('evidencias_audios', 'duration')
    op.drop_column('evidencias_audios', 'size')
    op.drop_column('evidencias_audios', 'mime_type')
    op.drop_column('evidencias_audios', 'file_type')
    op.drop_column('evidencias_audios', 'file_name')
    
    # Eliminar foreign keys y índices de evidencias_imagenes
    op.drop_constraint('fk_evidencias_imagenes_uploaded_by', 'evidencias_imagenes', type_='foreignkey')
    op.drop_index(op.f('ix_evidencias_imagenes_uploaded_by'), table_name='evidencias_imagenes')
    
    # Renombrar columna file_url a imagen_url
    op.alter_column('evidencias_imagenes', 'file_url', new_column_name='imagen_url')
    
    # Eliminar columnas agregadas
    op.drop_column('evidencias_imagenes', 'created_at')
    op.drop_column('evidencias_imagenes', 'uploaded_by')
    op.drop_column('evidencias_imagenes', 'size')
    op.drop_column('evidencias_imagenes', 'mime_type')
    op.drop_column('evidencias_imagenes', 'file_type')
    op.drop_column('evidencias_imagenes', 'file_name')
    
    # Eliminar foreign keys y índices de vehiculos_imagenes
    op.drop_constraint('fk_vehiculos_imagenes_uploaded_by', 'vehiculos_imagenes', type_='foreignkey')
    op.drop_constraint('fk_vehiculos_imagenes_vehiculo_id', 'vehiculos_imagenes', type_='foreignkey')
    op.drop_index(op.f('ix_vehiculos_imagenes_uploaded_by'), table_name='vehiculos_imagenes')
    op.drop_index(op.f('ix_vehiculos_imagenes_vehiculo_id'), table_name='vehiculos_imagenes')
    
    # Eliminar tabla
    op.drop_table('vehiculos_imagenes')
