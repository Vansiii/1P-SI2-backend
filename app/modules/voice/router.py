"""
Voice endpoints — transcripción de audio y comandos de voz.
"""
from fastapi import APIRouter, Depends

from ...core.dependencies import require_feature
from ...core.responses import success_response
from ...shared.dependencies.auth import get_current_user
from .service import VoiceService
from .schemas import VoiceReportRequest, VoiceCommandRequest

router = APIRouter(prefix="/voice", tags=["Voice Commands"])


@router.post("/transcribe", dependencies=[Depends(require_feature('enable_voice_reports'))])
async def transcribe_audio(
    body: VoiceReportRequest,
    current_user=Depends(get_current_user),
):
    svc = VoiceService()
    texto = await svc.transcribe_audio(body.audio_base64, body.mime_type)
    return success_response(data={"texto": texto}, message="Audio transcrito")


@router.post("/command", dependencies=[Depends(require_feature('enable_voice_reports'))])
async def process_command(
    body: VoiceCommandRequest,
    current_user=Depends(get_current_user),
):
    role = getattr(current_user, 'user_type', 'client')
    svc = VoiceService()
    result = await svc.process_text(body.texto, role)
    return success_response(data=result, message="Comando interpretado")


@router.post("/report", dependencies=[Depends(require_feature('enable_voice_reports'))])
async def process_voice_report(
    body: VoiceReportRequest,
    current_user=Depends(get_current_user),
):
    role = getattr(current_user, 'user_type', 'client')
    svc = VoiceService()
    result = await svc.process_audio(body.audio_base64, body.mime_type, role)
    return success_response(data=result, message="Audio procesado")
