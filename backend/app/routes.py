from fastapi import APIRouter, UploadFile

from . import actions
from .schemas import ActionResponse, ClusterConfig, CreateRequest, Health, MilestoneView, ResolveRequest, Ruleset

router = APIRouter(prefix="/api")


@router.get("/config")
def cluster_config() -> ClusterConfig:
    return actions.cluster_config()


@router.get("/health")
async def health() -> Health:
    return await actions.health()


@router.get("/rulesets")
def list_rulesets() -> list[Ruleset]:
    return list(actions.RULESETS.values())


@router.post("/milestones")
async def create_milestone(request: CreateRequest) -> ActionResponse:
    return await actions.create(request)


@router.get("/milestones/{address}")
async def get_milestone(address: str) -> MilestoneView:
    return await actions.view(address)


@router.post("/milestones/{address}/submit")
async def submit(address: str, file: UploadFile) -> ActionResponse:
    return await actions.submit(address, await file.read())


@router.post("/milestones/{address}/claim")
async def claim(address: str) -> ActionResponse:
    return await actions.claim(address)


@router.post("/milestones/{address}/dispute")
async def dispute(address: str) -> ActionResponse:
    return await actions.dispute(address)


@router.post("/milestones/{address}/resolve")
async def resolve(address: str, request: ResolveRequest) -> ActionResponse:
    return await actions.resolve(address, request.pay_contractor)


@router.post("/milestones/{address}/refund")
async def refund(address: str) -> ActionResponse:
    return await actions.refund(address)


@router.post("/milestones/{address}/attack/lenient-ruleset")
async def attack_lenient_ruleset(address: str, file: UploadFile) -> ActionResponse:
    return await actions.attack_lenient_ruleset(address, await file.read())
