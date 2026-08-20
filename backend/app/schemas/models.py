from pydantic import BaseModel, Field

class AnalysisCreate(BaseModel):
    original_image_id: str
    enhanced_image_id: str
    label: str | None = Field(default=None, max_length=120)

class ImageUploadResponse(BaseModel):
    id: str
    filename: str
    sha256: str
    width: int
    height: int
    content_type: str

class AnalysisCreateResponse(BaseModel):
    id: str
    status: str

class ReferenceAttach(BaseModel):
    dataset_id: str

class AlignmentCreate(BaseModel):
    image_points: list[list[float]]
    reference_points: list[list[float]]
    validation_image_points: list[list[float]] | None = None
    validation_reference_points: list[list[float]] | None = None

class VerifyRequest(BaseModel):
    mission_profile: str = "SCIENTIFIC_VISUALIZATION"

class NavigatorQuery(BaseModel):
    question: str
    analysis_id: str | None = None
    feature_id: str | None = None
