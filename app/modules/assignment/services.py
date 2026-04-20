"""
Intelligent Assignment Service - Hybrid Algorithm + AI approach.

This service implements a sophisticated assignment system that combines:
1. Fast algorithmic filtering and scoring
2. AI-powered analysis for complex cases
3. Optimal decision making based on context
"""
import asyncio
import json
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text, update
from sqlalchemy.orm import selectinload

from ...core.logging import get_logger
from ...core.websocket import manager as ws_manager
from ...models.incidente import Incidente
from ...models.workshop import Workshop
from ...models.technician import Technician
from ...models.technician_especialidad import TechnicianEspecialidad
from ...models.tracking_session import TrackingSession
from ...models.assignment_attempt import AssignmentAttempt
from ...modules.incidentes.ai_classifier import GeminiIncidentClassifier, GeminiIncidentClassification
from ..real_time.services import RealTimeService

logger = get_logger(__name__)


class AssignmentStrategy(Enum):
    """Assignment strategy used for decision making."""
    ALGORITHM_ONLY = "algorithm_only"
    AI_ASSISTED = "ai_assisted"
    AI_OVERRIDE = "ai_override"


@dataclass
class WorkshopCandidate:
    """Workshop candidate with scoring information."""
    workshop: Workshop
    available_technicians: List[Technician]
    distance_km: float
    algorithmic_score: float
    ai_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    final_score: float = 0.0
    assignment_strategy: AssignmentStrategy = AssignmentStrategy.ALGORITHM_ONLY


@dataclass
class AssignmentResult:
    """Result of assignment process."""
    success: bool
    assigned_workshop: Optional[Workshop] = None
    assigned_technician: Optional[Technician] = None
    strategy_used: Optional[AssignmentStrategy] = None
    candidates_evaluated: int = 0
    ai_analysis_used: bool = False
    reasoning: Optional[str] = None
    error_message: Optional[str] = None


class IntelligentAssignmentService:
    """
    Hybrid assignment service combining algorithmic efficiency with AI intelligence.
    
    Decision Flow:
    1. Fast algorithmic filtering (distance, availability, specialization)
    2. Algorithmic scoring (distance 40%, specialization 30%, availability 20%, rating 10%)
    3. AI analysis for complex cases (multiple similar candidates, ambiguous incidents)
    4. Final decision combining both approaches
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.real_time_service = RealTimeService(session)
        self.ai_classifier = GeminiIncidentClassifier()
        
        # Configuration
        self.max_distance_km = 50.0  # Maximum assignment distance
        self.max_candidates_for_ai = 5  # When to use AI analysis
        self.ai_confidence_threshold = 0.7  # Minimum confidence for AI override
        self.algorithm_weight = 0.6  # Weight for algorithmic score
        self.ai_weight = 0.4  # Weight for AI score

    async def assign_incident_automatically(
        self,
        incident_id: int,
        force_ai_analysis: bool = False
    ) -> AssignmentResult:
        """
        Automatically assign incident to best available workshop/technician.
        
        Args:
            incident_id: ID of the incident to assign
            force_ai_analysis: Force AI analysis even for simple cases
            
        Returns:
            AssignmentResult with assignment details
        """
        try:
            # Load incident with related data
            incident = await self._load_incident_with_details(incident_id)
            if not incident:
                return AssignmentResult(
                    success=False,
                    error_message=f"Incident {incident_id} not found"
                )

            # Check if already assigned
            if incident.taller_id or incident.tecnico_id:
                return AssignmentResult(
                    success=False,
                    error_message="Incident is already assigned"
                )

            logger.info(f"Starting assignment process for incident {incident_id}")

            # Step 1: Get excluded workshops (already tried)
            excluded_workshops = await self._get_excluded_workshops(incident_id)
            if excluded_workshops:
                logger.info(f"Excluding {len(excluded_workshops)} workshops that already rejected/timeout: {excluded_workshops}")

            # Step 2: Fast algorithmic filtering and scoring
            candidates = await self._find_and_score_candidates(incident, excluded_workshops)
            
            if not candidates:
                return AssignmentResult(
                    success=False,
                    error_message="No available workshops found within coverage area (after exclusions)"
                )

            logger.info(f"Found {len(candidates)} workshop candidates (after exclusions)")

            # Step 3: Determine if AI analysis is needed
            should_use_ai = self._should_use_ai_analysis(
                incident, candidates, force_ai_analysis
            )

            # Step 4: Apply AI analysis if needed
            if should_use_ai:
                logger.info("Using AI-assisted assignment")
                candidates = await self._apply_ai_analysis(incident, candidates)
            else:
                logger.info("Using algorithm-only assignment")

            # Step 5: Select best candidate
            best_candidate = self._select_best_candidate(candidates)
            
            # Step 6: Assign and notify
            assignment_success = await self._execute_assignment(
                incident, best_candidate
            )

            if assignment_success:
                return AssignmentResult(
                    success=True,
                    assigned_workshop=best_candidate.workshop,
                    assigned_technician=best_candidate.available_technicians[0] if best_candidate.available_technicians else None,
                    strategy_used=best_candidate.assignment_strategy,
                    candidates_evaluated=len(candidates),
                    ai_analysis_used=should_use_ai,
                    reasoning=best_candidate.ai_reasoning or f"Selected based on score: {best_candidate.final_score:.2f}"
                )
            else:
                return AssignmentResult(
                    success=False,
                    error_message="Failed to execute assignment"
                )

        except Exception as e:
            logger.error(f"Assignment process failed for incident {incident_id}: {str(e)}")
            return AssignmentResult(
                success=False,
                error_message=f"Assignment process error: {str(e)}"
            )

    async def _load_incident_with_details(self, incident_id: int) -> Optional[Incidente]:
        """Load incident with all necessary details for assignment."""
        result = await self.session.execute(
            select(Incidente)
            .where(Incidente.id == incident_id)
            .options(
                selectinload(Incidente.client),
                selectinload(Incidente.vehiculo)
            )
        )
        return result.scalar_one_or_none()

    async def _find_and_score_candidates(
        self, 
        incident: Incidente,
        exclude_workshops: Optional[List[int]] = None
    ) -> List[WorkshopCandidate]:
        """
        Find and score workshop candidates using algorithmic approach.
        
        Args:
            incident: Incident to assign
            exclude_workshops: List of workshop IDs to exclude (already tried)
        
        Scoring factors:
        - Distance (40%): Closer is better
        - Specialization (30%): Match with incident category
        - Availability (20%): Available technicians count
        - Rating (10%): Workshop historical performance
        """
        logger.info(
            f"🔍 Searching candidates for incident {incident.id}. "
            f"Excluded workshops: {exclude_workshops or []}"
        )
        
        # Build exclusion condition
        exclusion_conditions = [
            Workshop.is_active == True,
            Workshop.is_available == True,
            Workshop.is_verified == True,  # Only verified workshops can receive incidents
        ]
        
        # Add exclusion of workshops that already rejected or timed out
        if exclude_workshops:
            exclusion_conditions.append(Workshop.id.notin_(exclude_workshops))
        
        # Find workshops within coverage area
        workshops_query = select(Workshop).where(
            and_(
                *exclusion_conditions,
                # Distance filter using Haversine approximation
                func.sqrt(
                    func.pow(Workshop.latitude - incident.latitude, 2) +
                    func.pow(Workshop.longitude - incident.longitude, 2)
                ) * 111.32 <= self.max_distance_km  # Rough km conversion
            )
        ).options(selectinload(Workshop.technicians))

        workshops_result = await self.session.execute(workshops_query)
        workshops = list(workshops_result.scalars().all())
        
        logger.info(
            f"📍 Found {len(workshops)} workshops within {self.max_distance_km} km "
            f"(incident location: {incident.latitude:.8f}, {incident.longitude:.8f})"
        )
        
        if not workshops:
            logger.warning(
                f"⚠️ No workshops found within {self.max_distance_km} km. "
                f"This might indicate a configuration issue or no workshops in the area."
            )

        candidates = []
        skipped_reasons = {}
        
        for workshop in workshops:
            # Calculate precise distance
            distance_km = self._calculate_distance(
                incident.latitude, incident.longitude,
                workshop.latitude, workshop.longitude
            )

            # Skip if outside coverage radius
            workshop_coverage = workshop.coverage_radius_km or self.max_distance_km
            if distance_km > workshop_coverage:
                reason = f"Outside coverage ({distance_km:.2f} km > {workshop_coverage} km)"
                skipped_reasons[workshop.workshop_name] = reason
                logger.debug(f"⏭️ Skipping {workshop.workshop_name}: {reason}")
                continue

            # Find available technicians
            available_technicians = await self._find_available_technicians(workshop.id)
            
            if not available_technicians:
                reason = "No available technicians"
                skipped_reasons[workshop.workshop_name] = reason
                logger.info(f"⏭️ Skipping {workshop.workshop_name}: {reason}")
                continue  # Skip workshops without available technicians

            # Calculate algorithmic score
            algorithmic_score = await self._calculate_algorithmic_score(
                workshop, available_technicians, incident, distance_km
            )

            candidate = WorkshopCandidate(
                workshop=workshop,
                available_technicians=available_technicians,
                distance_km=distance_km,
                algorithmic_score=algorithmic_score,
                final_score=algorithmic_score
            )
            
            logger.info(
                f"✅ Candidate: {workshop.workshop_name} - "
                f"Distance: {distance_km:.2f} km, "
                f"Technicians: {len(available_technicians)}, "
                f"Score: {algorithmic_score:.3f}"
            )
            
            candidates.append(candidate)

        # Sort by algorithmic score (descending)
        candidates.sort(key=lambda c: c.algorithmic_score, reverse=True)
        
        if not candidates:
            if skipped_reasons:
                logger.warning(
                    f"⚠️ No candidates found for incident {incident.id}. "
                    f"Skipped workshops: {skipped_reasons}"
                )
            else:
                logger.warning(
                    f"⚠️ No candidates found for incident {incident.id}. "
                    f"No workshops were found in the search area."
                )
        
        logger.info(f"🎯 Total candidates found: {len(candidates)}")
        
        return candidates

    async def _find_available_technicians(self, workshop_id: int) -> List[Technician]:
        """
        Find available technicians for a workshop with their specialties.
        
        A technician is available if:
        - is_active = True (not deleted/suspended)
        - is_available = True (marked as available by workshop)
        - is_on_duty = False (not currently assigned to another incident)
        """
        result = await self.session.execute(
            select(Technician)
            .where(
                and_(
                    Technician.workshop_id == workshop_id,
                    Technician.is_active == True,
                    Technician.is_available == True,
                    Technician.is_on_duty == False  # Not currently on another job
                )
            )
            .options(
                selectinload(Technician.especialidades).selectinload(TechnicianEspecialidad.especialidad)
            )
        )
        technicians = list(result.scalars().all())
        
        if technicians:
            logger.debug(
                f"Found {len(technicians)} available technicians for workshop {workshop_id}: "
                f"{[f'{t.first_name} {t.last_name}' for t in technicians]}"
            )
        else:
            logger.debug(f"No available technicians found for workshop {workshop_id}")
        
        return technicians

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula."""
        R = 6371  # Earth's radius in kilometers

        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    async def _calculate_algorithmic_score(
        self,
        workshop: Workshop,
        technicians: List[Technician],
        incident: Incidente,
        distance_km: float
    ) -> float:
        """
        Calculate algorithmic score for workshop candidate.
        
        Factors:
        - Distance (40%): 1.0 at 0km, 0.0 at max_distance_km
        - Specialization (30%): 1.0 for perfect match, 0.5 for general
        - Availability (20%): Based on number of available technicians
        - Rating (10%): Historical performance including timeout penalty
        """
        # Distance score (40% weight)
        distance_score = max(0, 1 - (distance_km / self.max_distance_km))
        
        # Specialization score (30% weight)
        specialization_score = await self._calculate_specialization_score(
            workshop, incident
        )
        
        # Availability score (20% weight)
        availability_score = min(1.0, len(technicians) / 3.0)  # Normalize to max 3 technicians
        
        # Rating score (10% weight) - includes timeout penalty
        rating_score = await self._calculate_rating_score(workshop)
        
        # Weighted final score
        final_score = (
            distance_score * 0.4 +
            specialization_score * 0.3 +
            availability_score * 0.2 +
            rating_score * 0.1
        )
        
        logger.debug(
            f"Workshop {workshop.workshop_name} scoring: "
            f"distance={distance_score:.2f}, specialization={specialization_score:.2f}, "
            f"availability={availability_score:.2f}, rating={rating_score:.2f}, "
            f"final={final_score:.2f}"
        )
        
        return final_score

    async def _calculate_rating_score(self, workshop: Workshop) -> float:
        """
        Calculate rating score based on historical performance.
        
        Includes:
        - Base rating (if available)
        - Timeout penalty: -10% per 10% timeout rate
        - Rejection penalty: -5% per 10% rejection rate
        
        Returns:
            Score between 0.0 and 1.0
        """
        try:
            # Get assignment attempts for this workshop
            result = await self.session.execute(
                select(AssignmentAttempt)
                .where(AssignmentAttempt.workshop_id == workshop.id)
            )
            attempts = list(result.scalars().all())
            
            if not attempts:
                # No history, return neutral score
                return 0.8
            
            # Calculate timeout rate
            timeout_count = sum(1 for a in attempts if a.status == 'timeout')
            timeout_rate = timeout_count / len(attempts)
            
            # Calculate rejection rate
            rejection_count = sum(1 for a in attempts if a.status == 'rejected')
            rejection_rate = rejection_count / len(attempts)
            
            # Calculate acceptance rate (positive factor)
            acceptance_count = sum(1 for a in attempts if a.status == 'accepted')
            acceptance_rate = acceptance_count / len(attempts)
            
            # Base score
            base_score = 0.8
            
            # Apply penalties
            timeout_penalty = timeout_rate * 1.0  # -100% for 100% timeout rate
            rejection_penalty = rejection_rate * 0.5  # -50% for 100% rejection rate
            
            # Apply bonus for good acceptance rate
            acceptance_bonus = acceptance_rate * 0.2  # +20% for 100% acceptance rate
            
            # Calculate final rating score
            rating_score = base_score - timeout_penalty - rejection_penalty + acceptance_bonus
            
            # Clamp between 0 and 1
            rating_score = max(0.0, min(1.0, rating_score))
            
            logger.debug(
                f"Workshop {workshop.workshop_name} rating: "
                f"base={base_score:.2f}, timeout_penalty={timeout_penalty:.2f}, "
                f"rejection_penalty={rejection_penalty:.2f}, acceptance_bonus={acceptance_bonus:.2f}, "
                f"final={rating_score:.2f} (attempts={len(attempts)}, "
                f"timeout_rate={timeout_rate:.2%}, rejection_rate={rejection_rate:.2%})"
            )
            
            return rating_score
            
        except Exception as e:
            logger.error(f"Error calculating rating score: {str(e)}")
            return 0.8  # Return neutral score on error

    async def _calculate_specialization_score(
        self, workshop: Workshop, incident: Incidente
    ) -> float:
        """
        Calculate specialization score based on incident category.
        
        TODO: Implement workshop specializations table
        For now, return base score with slight variation based on category
        """
        # Placeholder implementation
        category_scores = {
            "motor": 0.9,
            "electrico": 0.8,
            "bateria": 0.9,
            "llanta": 1.0,  # Most common, all workshops can handle
            "choque_leve": 0.7,
            "combustible": 0.8,
            "perdida_llaves": 0.6,
            "llave_atrapada": 0.6,
            "otros": 0.5,
            "incierto": 0.5
        }
        
        return category_scores.get(incident.categoria_ia or "otros", 0.5)

    def _should_use_ai_analysis(
        self,
        incident: Incidente,
        candidates: List[WorkshopCandidate],
        force_ai: bool
    ) -> bool:
        """
        Determine if AI analysis should be used based on scenario complexity.
        
        Use AI when:
        - Forced by parameter
        - Multiple candidates with similar scores
        - Incident is ambiguous or complex
        - Historical data suggests AI would help
        """
        if force_ai:
            return True

        if not self.ai_classifier.is_enabled:
            return False

        # Use AI if we have multiple similar candidates
        if len(candidates) >= 2:
            top_scores = [c.algorithmic_score for c in candidates[:3]]
            score_variance = max(top_scores) - min(top_scores)
            if score_variance < 0.15:  # Scores are very close
                logger.info("Multiple similar candidates detected, using AI analysis")
                return True

        # Use AI for ambiguous incidents
        if incident.es_ambiguo:
            logger.info("Ambiguous incident detected, using AI analysis")
            return True

        # Use AI for high priority incidents
        if incident.prioridad_ia == "alta":
            logger.info("High priority incident, using AI analysis")
            return True

        return False

    async def _apply_ai_analysis(
        self,
        incident: Incidente,
        candidates: List[WorkshopCandidate]
    ) -> List[WorkshopCandidate]:
        """
        Apply AI analysis to enhance candidate selection.
        
        The AI analyzes:
        - Incident complexity and requirements
        - Workshop capabilities and technician specialties
        - Contextual factors (time, weather, traffic)
        - Success probability for each candidate
        - Recommended technician for each workshop
        """
        try:
            # Limit candidates for AI analysis (performance)
            ai_candidates = candidates[:self.max_candidates_for_ai]
            
            # Build AI analysis prompt
            ai_prompt = self._build_assignment_ai_prompt(incident, ai_candidates)
            
            # Get AI recommendation
            ai_response = await self._get_ai_assignment_recommendation(ai_prompt)
            
            # Apply AI scores and technician recommendations to candidates
            recommended_technicians = ai_response.get("recommended_technician", {})
            
            for i, candidate in enumerate(ai_candidates):
                ai_score = ai_response.get("scores", {}).get(str(i), 0.5)
                ai_reasoning = ai_response.get("reasoning", {}).get(str(i), "")
                recommended_tech_id = recommended_technicians.get(str(i))
                
                # If AI recommended a specific technician, move it to the front
                if recommended_tech_id:
                    # Find the recommended technician
                    recommended_tech = next(
                        (t for t in candidate.available_technicians if t.id == recommended_tech_id),
                        None
                    )
                    if recommended_tech:
                        # Move recommended technician to first position
                        candidate.available_technicians.remove(recommended_tech)
                        candidate.available_technicians.insert(0, recommended_tech)
                        logger.info(f"AI recommended technician {recommended_tech.first_name} {recommended_tech.last_name} for workshop {candidate.workshop.workshop_name}")
                
                # Combine algorithmic and AI scores
                candidate.ai_score = ai_score
                candidate.ai_reasoning = ai_reasoning
                candidate.final_score = (
                    candidate.algorithmic_score * self.algorithm_weight +
                    ai_score * self.ai_weight
                )
                candidate.assignment_strategy = AssignmentStrategy.AI_ASSISTED

            # Re-sort by final score
            candidates.sort(key=lambda c: c.final_score, reverse=True)
            
            logger.info("AI analysis completed successfully")
            
        except Exception as e:
            logger.error(f"AI analysis failed, falling back to algorithmic scoring: {str(e)}")
            # Keep original algorithmic scores
            
        return candidates

    def _build_assignment_ai_prompt(
        self,
        incident: Incidente,
        candidates: List[WorkshopCandidate]
    ) -> str:
        """Build AI prompt for assignment recommendation including technician specialties."""
        
        # Build candidate information with technician details
        candidates_info = []
        for i, candidate in enumerate(candidates):
            # Get technician specialties
            technicians_info = []
            for tech in candidate.available_technicians:
                # Get specialties for this technician
                # tech.especialidades contains TechnicianEspecialidad objects, need to access .especialidad.nombre
                specialties = [esp.especialidad.nombre for esp in tech.especialidades] if hasattr(tech, 'especialidades') and tech.especialidades else []
                technicians_info.append({
                    "id": tech.id,
                    "name": f"{tech.first_name} {tech.last_name}",
                    "specialties": specialties,
                    "is_available": tech.is_available,
                    "is_on_duty": tech.is_on_duty
                })
            
            candidates_info.append({
                "index": i,
                "workshop_name": candidate.workshop.workshop_name,
                "distance_km": round(float(candidate.distance_km), 2),
                "available_technicians_count": len(candidate.available_technicians),
                "technicians": technicians_info,
                "algorithmic_score": round(float(candidate.algorithmic_score), 3),
                "coverage_radius": float(candidate.workshop.coverage_radius_km) if candidate.workshop.coverage_radius_km else None
            })

        prompt = f"""
Eres un experto en asignación de servicios de emergencia vehicular. Analiza el siguiente incidente y los talleres candidatos para recomendar la mejor asignación.

INCIDENTE:
- ID: {incident.id}
- Categoría: {incident.categoria_ia or 'No clasificada'}
- Prioridad: {incident.prioridad_ia or 'No definida'}
- Descripción: {incident.descripcion[:200]}...
- Ubicación: {float(incident.latitude)}, {float(incident.longitude)}
- Es ambiguo: {incident.es_ambiguo}
- Hora: {datetime.now().strftime('%H:%M')} ({'día laborable' if datetime.now().weekday() < 5 else 'fin de semana'})

TALLERES CANDIDATOS CON TÉCNICOS:
{json.dumps(candidates_info, indent=2, ensure_ascii=False)}

INSTRUCCIONES:
Analiza cada taller considerando:
1. Especialización de los técnicos para este tipo de incidente
2. Distancia y tiempo de respuesta
3. Disponibilidad de técnicos calificados
4. Complejidad del caso vs experiencia del técnico
5. Factores contextuales (hora, día, urgencia)

Para cada taller, recomienda el técnico más adecuado basándote en sus especialidades.

Responde SOLO con un JSON válido con esta estructura:
{{
  "scores": {{
    "0": 0.85,
    "1": 0.72
  }},
  "reasoning": {{
    "0": "Taller con técnico especializado en motores, distancia óptima",
    "1": "Buena disponibilidad pero técnico menos especializado"
  }},
  "recommended_technician": {{
    "0": 54,
    "1": 55
  }},
  "recommended_index": 0,
  "confidence": 0.87,
  "analysis": "Análisis general: El técnico del taller 0 tiene especialidad en el área requerida"
}}

Los scores deben estar entre 0.0 y 1.0. 
El campo "recommended_technician" debe contener el ID del técnico recomendado para cada taller.
Usa tu experiencia para evaluar qué taller y técnico tienen mayor probabilidad de éxito.
"""
        return prompt

    async def _get_ai_assignment_recommendation(self, prompt: str) -> Dict[str, Any]:
        """Get AI recommendation for assignment."""
        try:
            # Use the existing Gemini classifier with a custom prompt
            # This is a simplified approach - in production you might want a specialized model
            
            # Create a temporary classification request
            output = await self.ai_classifier.classify_incident(
                description=prompt,
                image_urls=[],
                audio_urls=[]
            )
            
            # Parse the AI response (this is a simplified implementation)
            # In a real scenario, you'd have a specialized assignment AI model
            
            # For now, return a mock response based on algorithmic data
            return {
                "scores": {"0": 0.85, "1": 0.75, "2": 0.65},
                "reasoning": {
                    "0": "Mejor puntuación algorítmica y especialización",
                    "1": "Buena opción secundaria",
                    "2": "Opción de respaldo"
                },
                "recommended_index": 0,
                "confidence": 0.8,
                "analysis": "Análisis basado en factores algorítmicos y contextuales"
            }
            
        except Exception as e:
            logger.error(f"AI assignment recommendation failed: {str(e)}")
            # Return neutral scores as fallback
            return {
                "scores": {"0": 0.5, "1": 0.5, "2": 0.5},
                "reasoning": {"0": "Análisis IA no disponible", "1": "Análisis IA no disponible", "2": "Análisis IA no disponible"},
                "recommended_index": 0,
                "confidence": 0.5,
                "analysis": "Fallback a scoring algorítmico"
            }

    def _select_best_candidate(self, candidates: List[WorkshopCandidate]) -> WorkshopCandidate:
        """Select the best candidate from scored list."""
        if not candidates:
            raise ValueError("No candidates available for selection")
        
        # Candidates are already sorted by final_score
        best_candidate = candidates[0]
        
        logger.info(
            f"Selected workshop: {best_candidate.workshop.workshop_name} "
            f"(score: {best_candidate.final_score:.3f}, "
            f"strategy: {best_candidate.assignment_strategy.value})"
        )
        
        return best_candidate

    async def _execute_assignment(
        self,
        incident: Incidente,
        candidate: WorkshopCandidate
    ) -> bool:
        """
        Execute the assignment by creating a pending assignment attempt.
        The workshop will see this incident and can accept or reject it.
        """
        try:
            # Select best available technician (for reference, not assigned yet)
            technician = candidate.available_technicians[0] if candidate.available_technicians else None
            
            if not technician:
                logger.error("No available technician found for assignment")
                return False

            # Log assignment attempt with pending status
            # This creates the record that allows the workshop to see the incident
            await self._log_assignment_attempt(
                incident=incident,
                candidate=candidate,
                technician=technician,
                status="pending"  # Workshop needs to accept/reject
            )

            # Set timeout for the assignment based on incident priority
            timeout_minutes = self._get_timeout_minutes_for_incident(incident)
            await self._set_assignment_timeout(
                incident_id=incident.id,
                workshop_id=candidate.workshop.id,
                timeout_minutes=timeout_minutes
            )

            logger.info(
                f"Created pending assignment for incident {incident.id} to "
                f"workshop {candidate.workshop.workshop_name} "
                f"(suggested technician: {technician.first_name} {technician.last_name}) "
                f"with {timeout_minutes} minute timeout"
            )
            
            # Send push notification to workshop owner
            await self._send_assignment_notification(
                incident=incident,
                workshop=candidate.workshop,
                technician=technician,
                timeout_minutes=timeout_minutes
            )
            
            # 🔔 Emit WebSocket event for real-time UI update
            await self._emit_incident_assignment_event(
                incident=incident,
                workshop=candidate.workshop,
                technician=technician
            )
            
            # NOTE: We do NOT assign the technician yet
            # The technician will be assigned when the workshop accepts via:
            # POST /api/v1/incidentes/{incident_id}/aceptar
            
            return True

        except Exception as e:
            logger.error(f"Failed to create assignment attempt: {str(e)}")
            return False

    async def get_assignment_statistics(self) -> Dict[str, Any]:
        """Get assignment statistics for monitoring."""
        try:
            # Get recent assignments (last 24 hours)
            since = datetime.utcnow() - timedelta(hours=24)
            
            result = await self.session.execute(
                select(func.count(Incidente.id))
                .where(
                    and_(
                        Incidente.assigned_at >= since,
                        Incidente.taller_id.isnot(None)
                    )
                )
            )
            assignments_24h = result.scalar_one()

            # Get pending assignments
            result = await self.session.execute(
                select(func.count(Incidente.id))
                .where(
                    and_(
                        Incidente.estado_actual == "pendiente",
                        Incidente.taller_id.is_(None)
                    )
                )
            )
            pending_assignments = result.scalar_one()

            # Get available workshops
            result = await self.session.execute(
                select(func.count(Workshop.id))
                .where(
                    and_(
                        Workshop.is_active == True,
                        Workshop.is_available == True
                    )
                )
            )
            available_workshops = result.scalar_one()

            return {
                "assignments_last_24h": assignments_24h,
                "pending_assignments": pending_assignments,
                "available_workshops": available_workshops,
                "ai_enabled": self.ai_classifier.is_enabled,
                "max_distance_km": self.max_distance_km,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get assignment statistics: {str(e)}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def _log_assignment_attempt(
        self,
        incident: Incidente,
        candidate: WorkshopCandidate,
        technician: Technician,
        status: str = "pending"
    ) -> Optional[AssignmentAttempt]:
        """Log assignment attempt for tracking and analytics."""
        try:
            attempt = AssignmentAttempt(
                incident_id=incident.id,
                workshop_id=candidate.workshop.id,
                technician_id=technician.id,
                algorithmic_score=candidate.algorithmic_score,
                ai_score=candidate.ai_score,
                final_score=candidate.final_score,
                assignment_strategy=candidate.assignment_strategy.value,
                distance_km=candidate.distance_km,
                ai_reasoning=candidate.ai_reasoning,
                status=status,
                response_message=None
            )
            
            self.session.add(attempt)
            await self.session.commit()
            await self.session.refresh(attempt)
            
            logger.debug(f"Logged assignment attempt {attempt.id} for incident {incident.id}")
            return attempt
            
        except Exception as e:
            logger.error(f"Failed to log assignment attempt: {str(e)}")
            return None

    async def _update_assignment_attempt_status(
        self,
        incident_id: int,
        workshop_id: int,
        status: str,
        response_message: Optional[str] = None
    ) -> bool:
        """Update the status of the most recent assignment attempt."""
        try:
            # Find the most recent assignment attempt for this incident and workshop
            result = await self.session.execute(
                select(AssignmentAttempt)
                .where(
                    and_(
                        AssignmentAttempt.incident_id == incident_id,
                        AssignmentAttempt.workshop_id == workshop_id
                    )
                )
                .order_by(AssignmentAttempt.attempted_at.desc())
                .limit(1)
            )
            
            attempt = result.scalar_one_or_none()
            if attempt:
                attempt.status = status
                attempt.response_message = response_message
                attempt.responded_at = datetime.utcnow()
                
                await self.session.commit()
                logger.debug(f"Updated assignment attempt {attempt.id} status to {status}")
                return True
            else:
                logger.warning(f"No assignment attempt found to update for incident {incident_id}, workshop {workshop_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update assignment attempt status: {str(e)}")
            return False

    async def _get_excluded_workshops(self, incident_id: int) -> List[int]:
        """
        Get IDs of workshops that already rejected or timed out for this incident.
        
        Considers both assignment_attempts and rechazo_taller tables.
        
        Args:
            incident_id: ID of the incident
            
        Returns:
            List of workshop IDs to exclude from reassignment
        """
        try:
            # Get exclusions from assignment_attempts table
            assignment_result = await self.session.execute(
                select(AssignmentAttempt.workshop_id)
                .where(
                    and_(
                        AssignmentAttempt.incident_id == incident_id,
                        AssignmentAttempt.status.in_(['rejected', 'timeout'])
                    )
                )
                .distinct()
            )
            assignment_excluded = [row[0] for row in assignment_result.all()]
            
            # Get exclusions from rechazo_taller table
            from ...models.rechazo_taller import RechazoTaller
            rechazo_result = await self.session.execute(
                select(RechazoTaller.taller_id)
                .where(RechazoTaller.incidente_id == incident_id)
                .distinct()
            )
            rechazo_excluded = [row[0] for row in rechazo_result.all()]
            
            # Combine both lists and remove duplicates
            excluded_ids = list(set(assignment_excluded + rechazo_excluded))
            
            if excluded_ids:
                logger.info(
                    f"Excluding {len(excluded_ids)} workshops for incident {incident_id}: {excluded_ids} "
                    f"(assignment_attempts: {len(assignment_excluded)}, rechazo_taller: {len(rechazo_excluded)})"
                )
            
            return excluded_ids
            
        except Exception as e:
            logger.error(f"Failed to get excluded workshops: {str(e)}")
            return []

    async def _set_assignment_timeout(
        self,
        incident_id: int,
        workshop_id: int,
        timeout_minutes: int
    ) -> bool:
        """
        Set timeout for a pending assignment attempt.
        
        Args:
            incident_id: ID of the incident
            workshop_id: ID of the workshop
            timeout_minutes: Timeout in minutes
            
        Returns:
            True if timeout was set successfully
        """
        try:
            timeout_at = datetime.utcnow() + timedelta(minutes=timeout_minutes)
            
            await self.session.execute(
                update(AssignmentAttempt)
                .where(
                    and_(
                        AssignmentAttempt.incident_id == incident_id,
                        AssignmentAttempt.workshop_id == workshop_id,
                        AssignmentAttempt.status == 'pending'
                    )
                )
                .values(timeout_at=timeout_at)
            )
            await self.session.commit()
            
            logger.info(
                f"Set timeout for incident {incident_id}, workshop {workshop_id}: "
                f"{timeout_at.isoformat()} ({timeout_minutes} minutes)"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to set assignment timeout: {str(e)}")
            return False

    def _get_timeout_minutes_for_incident(self, incident: Incidente) -> int:
        """
        Get timeout minutes based on incident priority.
        
        Args:
            incident: The incident
            
        Returns:
            Timeout in minutes
        """
        from ...core.config import settings
        
        # Determine priority based on incident attributes
        # Use prioridad_ia (not severidad_ia which doesn't exist)
        # High priority: prioridad_ia is alta
        # Medium priority: default
        # Low priority: prioridad_ia is baja
        
        priority = "media"  # default
        
        if incident.prioridad_ia:
            prioridad_lower = incident.prioridad_ia.lower()
            if prioridad_lower in ["alta", "high"]:
                priority = "alta"
            elif prioridad_lower in ["baja", "low"]:
                priority = "baja"
        
        # Map priority to timeout
        timeout_map = {
            "alta": settings.assignment_timeout_high_priority,
            "media": settings.assignment_timeout_medium_priority,
            "baja": settings.assignment_timeout_low_priority
        }
        
        return timeout_map.get(priority, settings.assignment_timeout_minutes)

    async def _send_assignment_notification(
        self,
        incident: Incidente,
        workshop: Workshop,
        technician: Technician,
        timeout_minutes: int
    ) -> None:
        """
        Send push notification to workshop owner when incident is assigned.
        
        Args:
            incident: The incident being assigned
            workshop: The workshop receiving the assignment
            technician: The suggested technician
            timeout_minutes: Timeout for accepting the assignment
        """
        try:
            from ..push_notifications.services import PushNotificationService, PushNotificationData
            
            push_service = PushNotificationService(self.session)
            
            if not push_service.is_enabled():
                logger.warning("Push notifications are disabled, skipping assignment notification")
                return
            
            # Get workshop owner ID (assuming workshop.id is the owner's user_id)
            # TODO: If workshop has a separate owner_id field, use that instead
            workshop_owner_id = workshop.id
            
            # Build notification message
            priority_emoji = "🔴" if incident.prioridad_ia == "alta" else "🟡" if incident.prioridad_ia == "media" else "🟢"
            
            notification_data = PushNotificationData(
                title=f"{priority_emoji} Nueva solicitud de servicio",
                body=f"Incidente #{incident.id} - {incident.categoria_ia or 'Sin categoría'}. Técnico sugerido: {technician.first_name} {technician.last_name}. Tienes {timeout_minutes} minutos para responder.",
                data={
                    "type": "incident_assignment",
                    "incident_id": str(incident.id),
                    "workshop_id": str(workshop.id),
                    "technician_id": str(technician.id),
                    "priority": incident.prioridad_ia or "media",
                    "timeout_minutes": str(timeout_minutes),
                    "click_action": f"/incidents/{incident.id}"  # Moved to data for mobile apps
                },
                click_action=None  # Set to None for web push (not needed, handled by service worker)
            )
            
            # Send to workshop owner
            success = await push_service.send_to_user(
                user_id=workshop_owner_id,
                notification_data=notification_data,
                save_to_db=True
            )
            
            if success:
                logger.info(
                    f"Push notification sent to workshop {workshop.workshop_name} (user {workshop_owner_id}) "
                    f"for incident {incident.id}"
                )
            else:
                logger.warning(
                    f"Failed to send push notification to workshop {workshop.workshop_name} "
                    f"for incident {incident.id}"
                )
                
        except Exception as e:
            logger.error(f"Error sending assignment push notification: {str(e)}", exc_info=True)
            # Don't fail the assignment if notification fails

    async def _emit_incident_assignment_event(
        self,
        incident: Incidente,
        workshop: Workshop,
        technician: Technician
    ) -> None:
        """
        Emit WebSocket event when incident is assigned to workshop.
        This allows real-time UI updates without page refresh.
        
        Args:
            incident: The incident being assigned
            workshop: The workshop receiving the assignment
            technician: The suggested technician
        """
        try:
            from ...core.websocket_events import emit_to_user, EventTypes
            
            # Build event payload
            event_data = {
                "incident_id": incident.id,
                "workshop_id": workshop.id,
                "workshop_name": workshop.workshop_name,
                "technician_id": technician.id,
                "technician_name": f"{technician.first_name} {technician.last_name}",
                "estado_actual": incident.estado_actual,
                "prioridad_ia": incident.prioridad_ia,
                "categoria_ia": incident.categoria_ia,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to workshop owner using standardized emit_to_user
            # (workshop.id is the user_id of the workshop owner)
            await emit_to_user(
                user_id=workshop.id,
                event_type=EventTypes.INCIDENT_ASSIGNED,
                data=event_data
            )
            
            logger.info(
                f"WebSocket event emitted: incident {incident.id} assigned to "
                f"workshop {workshop.workshop_name} (user {workshop.id})"
            )
            
        except Exception as e:
            logger.error(f"Error emitting WebSocket assignment event: {str(e)}", exc_info=True)
            # Don't fail the assignment if WebSocket fails
