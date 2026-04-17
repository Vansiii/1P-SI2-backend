"""Incident AI orchestration service for queueing and processing UC10 tasks."""

from __future__ import annotations

import asyncio
import hashlib
import json

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    NotFoundException,
    ValidationException,
    get_logger,
    get_session_factory,
    get_settings,
)
from ...models.incident_ai_analysis import IncidentAIAnalysis
from .ai_classifier import GeminiIncidentClassification, GeminiIncidentClassifier
from .repository import IncidenteRepository

logger = get_logger(__name__)


class IncidentAIService:
    """Service to queue, process, and retrieve incident AI analyses."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = IncidenteRepository(session)
        self.classifier = GeminiIncidentClassifier()

    async def queue_incident_processing(
        self,
        incident_id: int,
        force_reprocess: bool = False,
    ) -> IncidentAIAnalysis:
        """Queue a new incident AI analysis or reuse existing completed result."""
        if not self.classifier.is_enabled:
            raise ValidationException(
                "Gemini integration is disabled. Configure GEMINI_API_KEY to enable UC10 processing"
            )

        incident = await self.repository.find_by_id(incident_id)
        if not incident:
            raise NotFoundException(resource_type="Incidente", resource_id=incident_id)

        description, image_urls, audio_urls = await self._load_incident_sources(incident_id)
        request_hash = self._build_request_hash(description, image_urls, audio_urls)

        if not force_reprocess:
            existing_analysis = await self._get_latest_completed_analysis_by_hash(
                incident_id=incident_id,
                request_hash=request_hash,
            )
            if existing_analysis:
                return existing_analysis

        next_attempt = await self._get_next_attempt_number(incident_id)
        queued_analysis = IncidentAIAnalysis(
            incident_id=incident_id,
            status="pending",
            model_name=self.classifier.model_name,
            prompt_version=self.classifier.prompt_version,
            request_hash=request_hash,
            attempt_number=next_attempt,
        )

        self.session.add(queued_analysis)
        await self.session.commit()
        await self.session.refresh(queued_analysis)

        return queued_analysis

    async def process_analysis_by_id(self, analysis_id: int) -> IncidentAIAnalysis:
        """Execute AI processing for one queued analysis id."""
        analysis = await self._get_analysis_by_id(analysis_id)
        if not analysis:
            raise NotFoundException(resource_type="Análisis IA", resource_id=analysis_id)

        if analysis.status in {"completed", "processing"}:
            return analysis

        analysis.status = "processing"
        analysis.error_code = None
        analysis.error_message = None
        await self.session.commit()

        try:
            incident = await self.repository.find_by_id(analysis.incident_id)
            if not incident:
                raise NotFoundException(resource_type="Incidente", resource_id=analysis.incident_id)

            description, image_urls, audio_urls = await self._load_incident_sources(analysis.incident_id)
            output = await self.classifier.classify_incident(
                description=description,
                image_urls=image_urls,
                audio_urls=audio_urls,
            )

            self._apply_classification_result(
                analysis=analysis,
                classification=output.classification,
                raw_response_json=output.raw_response_json,
                latency_ms=output.latency_ms,
                used_model_name=output.used_model_name,
            )
            self._sync_incident_fields(incident, output.classification)

            await self.session.commit()
            await self.session.refresh(analysis)
            return analysis
        except Exception as exc:
            await self._mark_analysis_failed(analysis, exc)
            logger.error(
                "Incident AI analysis failed",
                analysis_id=analysis.id,
                incident_id=analysis.incident_id,
                error=str(exc),
            )
            await self.session.refresh(analysis)
            return analysis

    async def get_latest_analysis_for_incident(self, incident_id: int) -> IncidentAIAnalysis | None:
        """Get latest analysis entry for an incident."""
        result = await self.session.execute(
            select(IncidentAIAnalysis)
            .where(IncidentAIAnalysis.incident_id == incident_id)
            .order_by(desc(IncidentAIAnalysis.created_at), desc(IncidentAIAnalysis.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_analysis_history(self, incident_id: int) -> list[IncidentAIAnalysis]:
        """List all analyses for an incident ordered by newest first."""
        result = await self.session.execute(
            select(IncidentAIAnalysis)
            .where(IncidentAIAnalysis.incident_id == incident_id)
            .order_by(desc(IncidentAIAnalysis.created_at), desc(IncidentAIAnalysis.id))
        )
        return list(result.scalars().all())

    @classmethod
    def schedule_incident_processing(cls, incident_id: int, force_reprocess: bool = False) -> None:
        """Schedule background queue+process flow for one incident."""
        settings = get_settings()
        if not settings.is_gemini_enabled:
            logger.debug(
                "Skipping automatic AI scheduling because Gemini is disabled",
                incident_id=incident_id,
            )
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "Cannot schedule AI processing because there is no running event loop",
                incident_id=incident_id,
            )
            return

        loop.create_task(cls._run_queue_and_process(incident_id, force_reprocess))

    @classmethod
    def dispatch_processing_by_analysis_id(cls, analysis_id: int) -> None:
        """Dispatch processing for a pre-queued analysis id."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "Cannot dispatch AI analysis because there is no running event loop",
                analysis_id=analysis_id,
            )
            return

        loop.create_task(cls._run_process_by_analysis_id(analysis_id))

    @classmethod
    async def _run_queue_and_process(cls, incident_id: int, force_reprocess: bool) -> None:
        """Background runner that queues then processes an incident analysis."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            service = cls(session)
            try:
                queued_analysis = await service.queue_incident_processing(
                    incident_id=incident_id,
                    force_reprocess=force_reprocess,
                )
                if queued_analysis.status == "completed" and not force_reprocess:
                    logger.info(
                        "Skipping AI processing because analysis is already up to date",
                        incident_id=incident_id,
                        analysis_id=queued_analysis.id,
                    )
                    return

                await service.process_analysis_by_id(queued_analysis.id)
            except Exception as exc:
                logger.error(
                    "Background queue+process failed",
                    incident_id=incident_id,
                    error=str(exc),
                )

    @classmethod
    async def _run_process_by_analysis_id(cls, analysis_id: int) -> None:
        """Background runner that processes a queued analysis id."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            service = cls(session)
            try:
                await service.process_analysis_by_id(analysis_id)
            except Exception as exc:
                logger.error(
                    "Background process-by-id failed",
                    analysis_id=analysis_id,
                    error=str(exc),
                )

    @staticmethod
    def serialize_analysis(analysis: IncidentAIAnalysis) -> dict[str, object]:
        """Convert an analysis model into API-safe payload."""
        return {
            "id": analysis.id,
            "incident_id": analysis.incident_id,
            "status": analysis.status,
            "model_name": analysis.model_name,
            "prompt_version": analysis.prompt_version,
            "request_hash": analysis.request_hash,
            "attempt_number": analysis.attempt_number,
            "category": analysis.category,
            "priority": analysis.priority,
            "summary": analysis.summary,
            "is_ambiguous": analysis.is_ambiguous,
            "confidence": float(analysis.confidence) if analysis.confidence is not None else None,
            "findings": IncidentAIService._safe_parse_list(analysis.findings_json),
            "missing_data": IncidentAIService._safe_parse_list(analysis.missing_data_json),
            "workshop_recommendation": analysis.workshop_recommendation,
            "error_code": analysis.error_code,
            "error_message": analysis.error_message,
            "latency_ms": analysis.latency_ms,
            "created_at": analysis.created_at,
            "updated_at": analysis.updated_at,
        }

    async def _get_analysis_by_id(self, analysis_id: int) -> IncidentAIAnalysis | None:
        """Get analysis by id."""
        result = await self.session.execute(
            select(IncidentAIAnalysis).where(IncidentAIAnalysis.id == analysis_id)
        )
        return result.scalar_one_or_none()

    async def _get_latest_completed_analysis_by_hash(
        self,
        incident_id: int,
        request_hash: str,
    ) -> IncidentAIAnalysis | None:
        """Get latest completed analysis with matching request hash."""
        result = await self.session.execute(
            select(IncidentAIAnalysis)
            .where(IncidentAIAnalysis.incident_id == incident_id)
            .where(IncidentAIAnalysis.request_hash == request_hash)
            .where(IncidentAIAnalysis.status == "completed")
            .order_by(desc(IncidentAIAnalysis.created_at), desc(IncidentAIAnalysis.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_next_attempt_number(self, incident_id: int) -> int:
        """Compute next analysis attempt number for an incident."""
        result = await self.session.execute(
            select(func.coalesce(func.max(IncidentAIAnalysis.attempt_number), 0)).where(
                IncidentAIAnalysis.incident_id == incident_id
            )
        )
        max_attempt_number = int(result.scalar_one())
        return max_attempt_number + 1

    async def _load_incident_sources(self, incident_id: int) -> tuple[str, list[str], list[str]]:
        """Load description and evidence URLs from incident records."""
        incident = await self.repository.find_by_id(incident_id)
        if not incident:
            raise NotFoundException(resource_type="Incidente", resource_id=incident_id)

        evidencias = await self.repository.find_evidencias_by_incidente(incident_id)

        image_urls: list[str] = []
        audio_urls: list[str] = []

        for evidencia in evidencias:
            if evidencia.tipo == "IMAGE":
                imagenes = await self.repository.find_imagenes_by_evidencia(evidencia.id)
                image_urls.extend(
                    imagen.file_url for imagen in imagenes if imagen.file_url
                )
            elif evidencia.tipo == "AUDIO":
                audios = await self.repository.find_audios_by_evidencia(evidencia.id)
                audio_urls.extend(
                    audio.file_url for audio in audios if audio.file_url
                )

        unique_image_urls = list(dict.fromkeys(image_urls))
        unique_audio_urls = list(dict.fromkeys(audio_urls))

        return incident.descripcion or "", unique_image_urls, unique_audio_urls

    @staticmethod
    def _build_request_hash(description: str, image_urls: list[str], audio_urls: list[str]) -> str:
        """Build deterministic hash from incident source payload."""
        hash_input = {
            "description": description.strip(),
            "images": image_urls,
            "audios": audio_urls,
        }
        serialized_input = json.dumps(hash_input, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized_input.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_parse_list(raw_json: str | None) -> list[str]:
        """Parse a JSON list string safely."""
        if not raw_json:
            return []

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        return [str(item) for item in parsed]

    def _apply_classification_result(
        self,
        analysis: IncidentAIAnalysis,
        classification: GeminiIncidentClassification,
        raw_response_json: str,
        latency_ms: int,
        used_model_name: str,
    ) -> None:
        """Write successful classifier output into analysis entity."""
        analysis.status = "completed"
        analysis.model_name = used_model_name
        analysis.category = classification.category
        analysis.priority = classification.priority
        analysis.summary = classification.summary
        analysis.is_ambiguous = classification.is_ambiguous
        analysis.confidence = classification.confidence
        analysis.findings_json = json.dumps(classification.findings, ensure_ascii=False)
        analysis.missing_data_json = json.dumps(classification.missing_data, ensure_ascii=False)
        analysis.workshop_recommendation = classification.workshop_recommendation
        analysis.raw_response_json = raw_response_json
        analysis.latency_ms = latency_ms
        analysis.error_code = None
        analysis.error_message = None

    @staticmethod
    def _sync_incident_fields(incident, classification: GeminiIncidentClassification) -> None:
        """Sync normalized classifier output into the existing incident columns."""
        incident.categoria_ia = classification.category
        incident.prioridad_ia = classification.priority
        incident.resumen_ia = classification.summary
        incident.es_ambiguo = classification.is_ambiguous

    async def _mark_analysis_failed(self, analysis: IncidentAIAnalysis, error: Exception) -> None:
        """Persist failed analysis state with truncated error metadata."""
        analysis.status = "failed"
        analysis.error_code = type(error).__name__
        analysis.error_message = str(error)[:1200]
        await self.session.commit()
