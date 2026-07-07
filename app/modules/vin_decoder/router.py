import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from ...core import get_logger, ExternalServiceException
from ...core.responses import create_success_response

logger = get_logger(__name__)

router = APIRouter(prefix="/vehicles", tags=["VIN Decoder"])


@router.get("/decode-vin/{vin}", response_model=dict)
async def decode_vin(vin: str):
    """
    Decodifica un número de chasis (VIN) usando la API pública gratuita de la NHTSA.
    Autocompleta marca, modelo y año del coche.
    """
    vin_clean = vin.strip().upper()
    if len(vin_clean) != 17:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El VIN debe tener exactamente 17 caracteres alfanuméricos."
        )

    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin_clean}?format=json"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ExternalServiceException("Error de conexión con la API pública de la NHTSA.")
            
            data = resp.json()
            results = data.get("Results", [])
            
            # Extract fields
            decoded_info = {
                "vin": vin_clean,
                "brand": None,
                "model": None,
                "year": None,
                "body_type": None
            }
            
            for item in results:
                variable = item.get("Variable")
                value = item.get("Value")
                if not value:
                    continue
                
                if variable == "Make":
                    decoded_info["brand"] = value.strip().capitalize()
                elif variable == "Model":
                    decoded_info["model"] = value.strip()
                elif variable == "Model Year":
                    try:
                        decoded_info["year"] = int(value.strip())
                    except ValueError:
                        pass
                elif variable == "Body Class":
                    decoded_info["body_type"] = value.strip()
            
            # Verification: Make and Model should at least be present
            if not decoded_info["brand"] and not decoded_info["model"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="El VIN no pudo ser decodificado o no se encontraron detalles válidos."
                )

            return create_success_response(
                data=decoded_info,
                message="VIN decodificado correctamente."
            )
            
    except httpx.HTTPError as e:
        logger.error("NHTSA API call timeout or failure", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La pasarela de la NHTSA no está disponible. Ingrese los detalles de forma manual."
        )
