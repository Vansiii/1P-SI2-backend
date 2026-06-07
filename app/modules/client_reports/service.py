"""
Client reports service — reportes para clientes con exportacion PDF/Excel.
"""
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from ...core.logging import get_logger
from ...core.exceptions import NotFoundException
from ...models.incidente import Incidente
from ...models.vehiculo import Vehiculo
from ...models.transaction import Transaction
from ...models.service_rating import ServiceRating
from ...models.workshop import Workshop

logger = get_logger(__name__)


class ClientReportsService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_summary(self, client_id: int) -> Dict:
        total_incidentes = await self.session.scalar(
            select(func.count(Incidente.id)).where(Incidente.client_id == client_id)
        ) or 0
        activos = await self.session.scalar(
            select(func.count(Incidente.id)).where(
                and_(
                    Incidente.client_id == client_id,
                    Incidente.estado_actual.in_(["pendiente", "asignado", "en_proceso"]),
                )
            )
        ) or 0
        total_gastado = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(Transaction.client_id == client_id, Transaction.status == "completed")
            )
        ) or 0.0
        total_vehiculos = await self.session.scalar(
            select(func.count(Vehiculo.id)).where(
                and_(Vehiculo.client_id == client_id, Vehiculo.is_active.is_(True))
            )
        ) or 0
        avg_rating = await self.session.scalar(
            select(func.avg(ServiceRating.rating)).where(ServiceRating.client_id == client_id)
        )
        return {
            "total_incidentes": total_incidentes,
            "total_gastado": float(total_gastado),
            "total_vehiculos": total_vehiculos,
            "incidentes_activos": activos,
            "rating_promedio": round(float(avg_rating), 1) if avg_rating else None,
        }

    async def get_spending(
        self, client_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=365)
        if start_date.tzinfo is not None:
            start_date = start_date.astimezone(timezone.utc).replace(tzinfo=None)
        if end_date.tzinfo is not None:
            end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)

        total = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(
                    Transaction.client_id == client_id,
                    Transaction.status == "completed",
                    Transaction.created_at >= start_date,
                    Transaction.created_at <= end_date,
                )
            )
        ) or 0.0
        count = await self.session.scalar(
            select(func.count(Transaction.id)).where(
                and_(
                    Transaction.client_id == client_id,
                    Transaction.status == "completed",
                    Transaction.created_at >= start_date,
                    Transaction.created_at <= end_date,
                )
            )
        ) or 0

        monthly = await self.session.execute(
            select(
                func.to_char(Transaction.created_at, 'YYYY-MM').label('mes'),
                func.sum(Transaction.amount).label('total'),
                func.count(Transaction.id).label('cantidad'),
            )
            .where(
                and_(
                    Transaction.client_id == client_id,
                    Transaction.status == "completed",
                )
            )
            .group_by(text('1'))
            .order_by(text('1 DESC'))
            .limit(12)
        )
        rows = [{"mes": r.mes, "total": float(r.total), "cantidad": r.cantidad} for r in monthly.all()]
        return {
            "total_gastado": float(total),
            "total_transacciones": count,
            "por_mes": rows,
        }

    async def get_vehicle_history(self, vehiculo_id: int, client_id: int) -> Dict:
        vehiculo = await self.session.scalar(
            select(Vehiculo).where(
                and_(Vehiculo.id == vehiculo_id, Vehiculo.client_id == client_id)
            )
        )
        if not vehiculo:
            raise NotFoundException("Vehículo no encontrado")

        result = await self.session.execute(
            select(
                Incidente.id,
                Incidente.created_at,
                Incidente.categoria_ia,
                Incidente.estado_actual,
                Workshop.workshop_name,
                func.coalesce(
                    select(func.sum(Transaction.amount)).where(
                        and_(Transaction.incident_id == Incidente.id, Transaction.status == "completed")
                    ).correlate(Incidente).scalar_subquery(),
                    0,
                ).label('costo'),
            )
            .outerjoin(Workshop, Workshop.id == Incidente.taller_id)
            .where(Incidente.vehiculo_id == vehiculo_id)
            .order_by(Incidente.created_at.desc())
        )
        servicios = [
            {
                "incidente_id": r.id,
                "fecha": r.created_at.isoformat() if r.created_at else "",
                "categoria": r.categoria_ia,
                "estado": r.estado_actual,
                "costo": float(r.costo) if r.costo else None,
                "taller_nombre": r.workshop_name,
            }
            for r in result.all()
        ]
        return {
            "vehiculo_id": vehiculo_id,
            "matricula": vehiculo.matricula,
            "total_servicios": len(servicios),
            "servicios": servicios,
        }

    # ---- PDF Export ----

    def _export_pdf(self, title: str, headers: List[str], rows: List[List[str]]) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch

        is_wide = len(headers) >= 5
        page = landscape(letter) if is_wide else letter
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=page, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        styles = getSampleStyleSheet()

        cell_style = ParagraphStyle('C', parent=styles['Normal'],
            fontSize=8, leading=10, fontName='Helvetica', wordWrap='CJK')
        header_style = ParagraphStyle('H', parent=styles['Normal'],
            fontSize=8, leading=10, fontName='Helvetica-Bold', textColor=colors.whitesmoke, wordWrap='CJK')

        elements = []
        elements.append(Paragraph(title, ParagraphStyle('T', parent=styles['Heading1'],
            fontSize=18, textColor=colors.HexColor('#1e293b'), spaceAfter=6, fontName='Helvetica-Bold')))
        elements.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} — MecánicoYa",
            ParagraphStyle('S', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748b'), spaceAfter=14)))
        elements.append(Spacer(1, 0.1 * inch))

        if not rows:
            elements.append(Paragraph("No hay datos para el período seleccionado.", styles['Normal']))
        else:
            table_data = [[Paragraph(h, header_style) for h in headers]]
            for row in rows:
                table_data.append([Paragraph(str(c), cell_style) for c in row])

            available_w = page[0] - 60
            num_cols = len(headers)
            col_widths = [available_w / num_cols] * num_cols
            # Give more space to description columns
            for i, h in enumerate(headers):
                hl = h.lower()
                if any(w in hl for w in ['mes', 'fecha', 'total', 'costo']):
                    col_widths[i] = available_w * 0.16
                elif any(w in hl for w in ['categoría', 'categoria', 'estado', 'taller']):
                    col_widths[i] = available_w * 0.22
                elif any(w in hl for w in ['indicador', 'valor', 'transacciones']):
                    col_widths[i] = available_w / num_cols
            total_w = sum(col_widths)
            if total_w > 0:
                col_widths = [w / total_w * available_w for w in col_widths]

            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(table)

        doc.build(elements)
        return buffer.getvalue()

    def _export_excel(self, title: str, headers: List[str], rows: List[List[str]]) -> bytes:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title[:31]
        ws.append(headers)
        for r in rows:
            ws.append(r)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ---- Public export methods ----

    async def export_summary(self, client_id: int, fmt: str) -> tuple[bytes, str, str]:
        data = await self.get_summary(client_id)
        rows = [[str(k), str(v)] for k, v in data.items()]
        if fmt == 'pdf':
            return self._export_pdf('Resumen General', ['Indicador', 'Valor'], rows), 'application/pdf', 'resumen'
        else:
            return self._export_excel('Resumen General', ['Indicador', 'Valor'], rows), \
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'resumen'

    async def export_spending(self, client_id: int, fmt: str) -> tuple[bytes, str, str]:
        data = await self.get_spending(client_id)
        rows = []
        for m in data.get('por_mes', []):
            rows.append([m['mes'], f"Bs. {m['total']:.2f}", str(m['cantidad'])])
        rows.append(['TOTAL', f"Bs. {data['total_gastado']:.2f}", str(data['total_transacciones'])])
        if fmt == 'pdf':
            return self._export_pdf('Reporte de Gastos', ['Mes', 'Total', 'Transacciones'], rows), 'application/pdf', 'gastos'
        else:
            return self._export_excel('Reporte de Gastos', ['Mes', 'Total', 'Transacciones'], rows), \
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'gastos'

    async def export_vehicle_history(self, vehiculo_id: int, client_id: int, fmt: str) -> tuple[bytes, str, str]:
        data = await self.get_vehicle_history(vehiculo_id, client_id)
        rows = []
        for s in data.get('servicios', []):
            rows.append([
                s['fecha'][:10] if s['fecha'] else '',
                s['categoria'] or 'N/A',
                s['estado'],
                s['taller_nombre'] or 'N/A',
                f"Bs. {s['costo']:.2f}" if s['costo'] else 'N/A',
            ])
        title = f"Historial — {data['matricula']}"
        headers = ['Fecha', 'Categoría', 'Estado', 'Taller', 'Costo']
        if fmt == 'pdf':
            return self._export_pdf(title, headers, rows), 'application/pdf', f"historial_{data['matricula']}"
        else:
            return self._export_excel(title, headers, rows), \
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', f"historial_{data['matricula']}"
