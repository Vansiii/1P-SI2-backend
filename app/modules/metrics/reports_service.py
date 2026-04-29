"""
Service for generating detailed reports and exporting to PDF/Excel.
"""
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, extract

from ...core.logging import get_logger

logger = get_logger(__name__)

class ReportsService:
    """
    Service for advanced reporting and metric calculation.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_naive_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Normalize datetime to naive UTC."""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _to_aware_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Normalize datetime to aware UTC."""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        return dt.replace(tzinfo=timezone.utc)

    async def get_incident_report(
        self,
        start_date: datetime,
        end_date: datetime,
        category_id: Optional[int] = None,
        status: Optional[str] = None,
        workshop_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get detailed incident report."""
        from ...models.incidente import Incidente
        from ...models.workshop import Workshop

        try:
            start_date = self._to_aware_utc(start_date)
            end_date = self._to_aware_utc(end_date)
            # Use outerjoin to include incidents without an assigned workshop
            query = select(Incidente).outerjoin(Workshop).where(
                and_(
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
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
                    "id": i.id,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                    "estado_actual": i.estado_actual,
                    "categoria_ia": i.categoria_ia,
                    "direccion_referencia": i.direccion_referencia,
                    "prioridad_ia": i.prioridad_ia
                } for i in incidents
            ]
        except Exception as e:
            logger.error(f"Error in get_incident_report: {e}", exc_info=True)
            return []

    async def get_financial_report(self, start_date: datetime, end_date: datetime, workshop_id: Optional[int] = None):
        """Get financial summary report."""
        from ...models.transaction import Transaction
        from ...models.workshop_balance import Withdrawal
        from ...models.financial_movement import WorkshopFinancialMovement

        try:
            start_date = self._to_naive_utc(start_date)
            end_date = self._to_naive_utc(end_date)
            
            trans_query = select(
                func.sum(Transaction.amount).label("total_collected"),
                func.sum(Transaction.commission).label("total_commission"),
                func.sum(Transaction.workshop_amount).label("total_workshop_net"),
                func.count(Transaction.id).label("transaction_count")
            ).where(
                and_(
                    Transaction.created_at >= start_date,
                    Transaction.created_at <= end_date,
                    Transaction.status == 'completed'
                )
            )

            if workshop_id:
                trans_query = trans_query.where(Transaction.workshop_id == workshop_id)

            result = await self.session.execute(trans_query)
            row = result.one_or_none()

            summary_total_collected = float(row.total_collected or 0) if row else 0
            summary_total_commission = float(row.total_commission or 0) if row else 0
            summary_total_workshop_net = float(row.total_workshop_net or 0) if row else 0
            summary_transaction_count = int(row.transaction_count or 0) if row else 0

            with_query = select(func.sum(Withdrawal.amount)).where(
                and_(
                    Withdrawal.completed_at >= start_date,
                    Withdrawal.completed_at <= end_date,
                    Withdrawal.status == 'paid'
                )
            )

            if workshop_id:
                with_query = with_query.where(Withdrawal.workshop_id == workshop_id)
            
            total_withdrawn = await self.session.scalar(with_query) or 0
            
            movements_query = select(WorkshopFinancialMovement).where(
                and_(
                    WorkshopFinancialMovement.created_at >= start_date,
                    WorkshopFinancialMovement.created_at <= end_date
                )
            )
            if workshop_id:
                movements_query = movements_query.where(WorkshopFinancialMovement.workshop_id == workshop_id)
            
            movements_result = await self.session.execute(movements_query)
            movements = movements_result.scalars().all()

            return {
                "summary": {
                    "total_collected": summary_total_collected,
                    "total_commission": summary_total_commission,
                    "total_workshop_net": summary_total_workshop_net,
                    "total_withdrawn": float(total_withdrawn or 0),
                    "transaction_count": summary_transaction_count
                },
                "movements": [
                    {
                        "id": m.id,
                        "amount": float(m.amount),
                        "movement_type": m.movement_type,
                        "description": m.description,
                        "created_at": m.created_at.isoformat() if m.created_at else None
                    } for m in movements
                ],
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                }
            }
        except Exception as e:
            logger.error(f"Error in get_financial_report: {e}", exc_info=True)
            return {"error": str(e), "summary": {}, "movements": []}

    async def get_performance_report(
        self,
        workshop_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get workshop performance metrics."""
        from ...models.incidente import Incidente
        from ...models.workshop import Workshop

        try:
            if not end_date:
                end_date = datetime.now(timezone.utc)
            if not start_date:
                start_date = end_date - timedelta(days=30)
                
            start_date = self._to_aware_utc(start_date)
            end_date = self._to_aware_utc(end_date)

            query = select(
                Workshop.id,
                Workshop.workshop_name,
                func.count(Incidente.id).label("total_incidents"),
                func.avg(func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60).label("avg_response_time"),
                func.avg(func.extract('epoch', Incidente.resolved_at - Incidente.assigned_at) / 60).label("avg_resolution_time")
            ).outerjoin(
                Incidente,
                and_(
                    Incidente.taller_id == Workshop.id,
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date
                )
            ).group_by(Workshop.id, Workshop.workshop_name)

            if workshop_id:
                query = query.where(Workshop.id == workshop_id)

            result = await self.session.execute(query)
            rows = result.all()

            return [
                {
                    "workshop_id": r.id,
                    "name": r.workshop_name,
                    "total_incidents": r.total_incidents,
                    "avg_response_min": round(float(r.avg_response_time or 0), 2),
                    "avg_resolution_min": round(float(r.avg_resolution_time or 0), 2)
                } for r in rows
            ]
        except Exception as e:
            logger.error(f"Error in get_performance_report: {e}", exc_info=True)
            return []

    async def export_to_excel(self, data: List[Dict], sheet_name: str = "Report") -> bytes:
        """Export list of dictionaries to Excel bytes."""
        try:
            import pandas as pd
            import io
            df = pd.DataFrame(data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)
            return output.getvalue()
        except ImportError:
            logger.error("Pandas or openpyxl not installed, cannot export to Excel")
            raise Exception("Funcionalidad de exportación a Excel no disponible en este entorno.")
        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}")
            raise e

    async def export_to_pdf(self, data: List[Dict], title: str = "Reporte de Sistema") -> bytes:
        """Export list of dictionaries to a premium PDF format."""
        import io
        from datetime import datetime
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
        except ImportError:
            logger.error("ReportLab not installed, cannot export to PDF")
            raise Exception("Funcionalidad de exportación a PDF no disponible en este entorno.")

        try:
            buffer = io.BytesIO()
            # Use landscape if data is wide
            is_wide = len(data[0].keys()) > 6 if data else False
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=landscape(letter) if is_wide else letter,
                rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
            )
            
            styles = getSampleStyleSheet()
            elements = []

            # Custom Styles
            title_style = ParagraphStyle(
                'PremiumTitle',
                parent=styles['Heading1'],
                fontSize=22,
                textColor=colors.HexColor('#1e293b'),
                spaceAfter=10,
                fontName='Helvetica-Bold'
            )
            
            subtitle_style = ParagraphStyle(
                'PremiumSubtitle',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#64748b'),
                spaceAfter=20
            )

            # Header
            elements.append(Paragraph(title, title_style))
            elements.append(Paragraph(f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
            elements.append(Spacer(1, 0.2 * inch))

            if not data:
                elements.append(Paragraph("No hay datos disponibles para este período.", styles['Normal']))
            else:
                # Prepare Table Data
                headers = list(data[0].keys())
                table_data = [headers]
                for item in data:
                    table_data.append([str(item.get(h, '')) for h in headers])

                # Create Table
                available_width = (landscape(letter)[0] if is_wide else letter[0]) - 80
                col_widths = [available_width / len(headers)] * len(headers)
                
                table = Table(table_data, colWidths=col_widths, repeatRows=1)
                
                # Table Style
                style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('TOPPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')])
                ])
                table.setStyle(style)
                elements.append(table)

            doc.build(elements)
            return buffer.getvalue()
        except Exception as e:
            logger.error(f"Error exporting to PDF: {e}")
            raise e
