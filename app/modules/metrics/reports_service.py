"""
Service for generating detailed reports and exporting to PDF/Excel.
"""
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ...core.logging import get_logger

logger = get_logger(__name__)

SPANISH_MONTHS = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

INCIDENT_HEADERS_ES = ['ID', 'Fecha', 'Estado', 'Categoría', 'Dirección', 'Prioridad']

PERFORMANCE_HEADERS_ES = ['ID Taller', 'Nombre', 'Total Incidentes', 'T. Respuesta (min)', 'T. Resolución (min)']

FINANCIAL_HEADERS_ES = ['Concepto', 'Monto (Bs.)']


class ReportsService:
    """Service for advanced reporting and metric calculation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_naive_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _to_aware_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=timezone.utc)

    async def get_incident_report(
        self, start_date: datetime, end_date: datetime,
        category_id: Optional[int] = None, status: Optional[str] = None,
        workshop_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        from ...models.incidente import Incidente
        from ...models.workshop import Workshop

        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)
        query = select(Incidente).outerjoin(Workshop).where(
            and_(Incidente.created_at >= start_date, Incidente.created_at <= end_date)
        )
        if category_id:
            query = query.where(Incidente.categoria_ia == str(category_id))
        if status:
            query = query.where(Incidente.estado_actual == status)
        if workshop_id:
            query = query.where(Incidente.taller_id == workshop_id)

        result = await self.session.execute(query)
        incidents = result.scalars().all()
        return [
            {
                "ID": i.id,
                "Fecha": i.created_at.strftime('%d/%m/%Y %H:%M') if i.created_at else '',
                "Estado": i.estado_actual or '',
                "Categoría": (i.categoria_ia or 'N/A').replace('_', ' ').title(),
                "Dirección": i.direccion_referencia or '',
                "Prioridad": i.prioridad_ia or 'N/A',
            } for i in incidents
        ]

    async def get_financial_report(
        self, start_date: datetime, end_date: datetime,
        workshop_id: Optional[int] = None,
    ):
        from ...models.transaction import Transaction
        from ...models.workshop_balance import Withdrawal
        from ...models.financial_movement import WorkshopFinancialMovement

        start_date = self._to_naive_utc(start_date)
        end_date = self._to_naive_utc(end_date)

        trans_query = select(
            func.sum(Transaction.amount).label("total_collected"),
            func.sum(Transaction.commission).label("total_commission"),
            func.sum(Transaction.workshop_amount).label("total_workshop_net"),
            func.count(Transaction.id).label("transaction_count"),
        ).where(and_(
            Transaction.created_at >= start_date, Transaction.created_at <= end_date,
            Transaction.status == 'completed',
        ))
        if workshop_id:
            trans_query = trans_query.where(Transaction.workshop_id == workshop_id)
        result = await self.session.execute(trans_query)
        row = result.one_or_none()

        stc = float(row.total_collected or 0) if row else 0
        stcm = float(row.total_commission or 0) if row else 0
        stwn = float(row.total_workshop_net or 0) if row else 0
        stx = int(row.transaction_count or 0) if row else 0

        with_query = select(func.sum(Withdrawal.amount)).where(and_(
            Withdrawal.completed_at >= start_date, Withdrawal.completed_at <= end_date,
            Withdrawal.status == 'paid',
        ))
        if workshop_id:
            with_query = with_query.where(Withdrawal.workshop_id == workshop_id)
        total_withdrawn = await self.session.scalar(with_query) or 0

        movements_query = select(WorkshopFinancialMovement).where(and_(
            WorkshopFinancialMovement.created_at >= start_date,
            WorkshopFinancialMovement.created_at <= end_date,
        ))
        if workshop_id:
            movements_query = movements_query.where(WorkshopFinancialMovement.workshop_id == workshop_id)
        movements_result = await self.session.execute(movements_query)
        movements = movements_result.scalars().all()

        return {
            "summary": {
                "total_collected": stc, "total_commission": stcm,
                "total_workshop_net": stwn, "total_withdrawn": float(total_withdrawn or 0),
                "transaction_count": stx,
            },
            "movements": [
                {"id": m.id, "amount": float(m.amount), "movement_type": m.movement_type,
                 "description": m.description,
                 "created_at": m.created_at.isoformat() if m.created_at else None}
                for m in movements
            ],
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        }

    async def get_performance_report(
        self, workshop_id: Optional[int] = None,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        from ...models.incidente import Incidente
        from ...models.workshop import Workshop

        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        start_date = self._to_aware_utc(start_date)
        end_date = self._to_aware_utc(end_date)

        query = select(
            Workshop.id, Workshop.workshop_name,
            func.count(Incidente.id).label("total_incidents"),
            func.avg(func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60).label("avg_response_time"),
            func.avg(func.extract('epoch', Incidente.resolved_at - Incidente.assigned_at) / 60).label("avg_resolution_time"),
        ).outerjoin(Incidente, and_(
            Incidente.taller_id == Workshop.id,
            Incidente.created_at >= start_date, Incidente.created_at <= end_date,
        )).group_by(Workshop.id, Workshop.workshop_name)

        if workshop_id:
            query = query.where(Workshop.id == workshop_id)

        result = await self.session.execute(query)
        rows = result.all()
        return [
            {
                "ID Taller": r.id,
                "Nombre": r.workshop_name,
                "Total Incidentes": r.total_incidents or 0,
                "T. Respuesta (min)": round(float(r.avg_response_time or 0), 1),
                "T. Resolución (min)": round(float(r.avg_resolution_time or 0), 1),
            } for r in rows
        ]

    # ---- Excel ----

    async def export_to_excel(self, data: List[Dict], sheet_name: str = "Report") -> bytes:
        import pandas as pd
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return output.getvalue()

    # ---- PDF ----

    async def export_to_pdf(self, data: List[Dict], title: str = "Reporte") -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, mm

        try:
            buffer = io.BytesIO()
            if not data:
                doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
                styles = getSampleStyleSheet()
                doc.build([Paragraph(title, styles['Heading1']),
                          Paragraph("No hay datos para el período seleccionado.", styles['Normal'])])
                return buffer.getvalue()

            headers = list(data[0].keys())
            num_cols = len(headers)
            is_wide = num_cols >= 5
            page = landscape(letter) if is_wide else letter
            doc = SimpleDocTemplate(buffer, pagesize=page, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            styles = getSampleStyleSheet()

            cell_style = ParagraphStyle('Cell', parent=styles['Normal'],
                fontSize=8, leading=10, fontName='Helvetica', wordWrap='CJK')

            elements = []
            elements.append(Paragraph(title, ParagraphStyle('T', parent=styles['Heading1'],
                fontSize=18, textColor=colors.HexColor('#1e293b'), spaceAfter=6, fontName='Helvetica-Bold')))
            elements.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} — MecánicoYa",
                ParagraphStyle('S', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#64748b'), spaceAfter=14)))
            elements.append(Spacer(1, 0.1 * inch))

            # Header row with bold Paragraphs
            header_style = ParagraphStyle('Hdr', parent=styles['Normal'],
                fontSize=8, leading=10, fontName='Helvetica-Bold', textColor=colors.whitesmoke, wordWrap='CJK')
            table_data = [[Paragraph(h, header_style) for h in headers]]

            for row in data:
                table_data.append([Paragraph(str(row.get(h, '')), cell_style) for h in headers])

            available_w = page[0] - 60

            # Smart column widths based on content type
            col_widths = []
            for i, h in enumerate(headers):
                hl = h.lower()
                if any(w in hl for w in ['id', 'código', 'codigo']):
                    col_widths.append(available_w * 0.06)
                elif any(w in hl for w in ['fecha', 'estado', 'prioridad', 'categoría', 'categoria', 't. ']):
                    col_widths.append(available_w * 0.14)
                elif any(w in hl for w in ['dirección', 'direccion', 'nombre']):
                    col_widths.append(available_w * 0.28)
                elif any(w in hl for w in ['descripción', 'descripcion']):
                    col_widths.append(available_w * 0.38)
                else:
                    col_widths.append(available_w / num_cols)

            # Normalize to fit available width
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
        except Exception as e:
            logger.error(f"Error exporting to PDF: {e}", exc_info=True)
            raise
