"""
Schemas for service ratings.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RatingCreate(BaseModel):
    """Schema for creating a service rating."""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=1000, description="Optional comment about the service")
    
    @field_validator('comment')
    @classmethod
    def validate_comment(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return None
        return v


class RatingResponse(BaseModel):
    """Schema for rating response."""
    id: int
    incident_id: int
    client_id: int
    workshop_id: int
    technician_id: Optional[int]
    rating: int
    comment: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class RatingWithDetails(RatingResponse):
    """Schema for rating with additional details."""
    client_name: Optional[str] = None
    workshop_name: Optional[str] = None
    technician_name: Optional[str] = None
    incident_description: Optional[str] = None


class WorkshopRatingStats(BaseModel):
    """Statistics for workshop ratings."""
    workshop_id: int
    workshop_name: str
    total_ratings: int
    average_rating: float
    rating_distribution: dict[int, int]  # {1: count, 2: count, ...}
    recent_ratings: list[RatingWithDetails]


class TechnicianRatingStats(BaseModel):
    """Statistics for technician ratings."""
    technician_id: int
    technician_name: str
    total_ratings: int
    average_rating: float
    rating_distribution: dict[int, int]
    recent_ratings: list[RatingWithDetails]
