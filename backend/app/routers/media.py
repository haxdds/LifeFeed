from fastapi import APIRouter, Depends, UploadFile, status

from ..models import User
from ..schemas import MediaOut
from ..security import get_current_user
from ..storage import save_upload

router = APIRouter(prefix="/api/media", tags=["media"])


@router.post("", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, _user: User = Depends(get_current_user)):
    return MediaOut(url=await save_upload(file))
