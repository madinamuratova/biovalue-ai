"""BioValue AI API and dashboard (FastAPI). Start it from the project folder and open http://127.0.0.1:8765:

    .venv/bin/python -m uvicorn backend.main:app --port 8765

Routes:
    GET  /api/health                     model name and whether the API key is configured
    GET  /api/project                    the demo inputs, the input presets (fictional demo, literature reference), pathways, rubric
    GET  /api/evidence                   the evidence library
    POST /api/preview                    validate inputs and return the deterministic profile and economics (no model)
    POST /api/runs                       start the four-agent workflow on the inputs (202); one run at a time
    GET  /api/runs/latest                the latest saved assessment
    GET  /api/runs/{run_id}              a run's status, live trace, and result when finished
    GET  /api/runs/{run_id}/report.md    the assessment as Markdown ("latest" works as run_id)
    GET  /api/runs/{run_id}/report.html  the assessment as standalone HTML
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import data
from backend.agents import AGENT_ORDER, AGENT_TITLES
from backend.agents import deterministic
from backend.config import DATA_DIR, MAX_REQUEST_BYTES, OUTPUT_DIR, STORE_RUN_INPUTS, default_run_config, model_name
from backend.safety import redact
from backend.inputs import InputError, build_project
from backend.report import render_html, render_markdown
from backend.scoring import assess_indicative_economics
from backend.trace import Trace, now
from backend.workflow import FinalAssessment, new_run_id, run_workflow

app = FastAPI(title="BioValue AI")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.state.model_factory = None  # tests swap in scripted models; None means the course model through Portkey
app.state.output_dir = OUTPUT_DIR
app.state.runs = {}
app.state.active_run = None
app.state.tasks = set()
app.state.store_inputs = STORE_RUN_INPUTS  # user inputs are kept in memory only, unless BIOVALUE_STORE_INPUTS=1


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Refuse oversized requests before they are read (input-size limit)."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        return JSONResponse(status_code=413, content={
            "message": f"The request is too large ({int(length):,} bytes; limit {MAX_REQUEST_BYTES:,}).", "errors": []})
    return await call_next(request)


class AssessmentInput(BaseModel):
    feedstock: dict | None = None  # same shape as data/demo_feedstock.json
    economic_assumptions: dict | None = None  # pathway id -> PathwayAssumptions


class RunState(BaseModel):
    run_id: str
    status: Literal["running", "complete", "partial", "failed", "error"]
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    trace: Trace
    result: FinalAssessment | None = None
    inputs: dict | None = None  # what the dashboard submitted; None for runs started from the command line


@app.exception_handler(InputError)
async def input_error(_, exc: InputError):
    return JSONResponse(status_code=422, content={"message": "Some inputs are not valid.", "errors": exc.errors})


def _project(body: AssessmentInput):
    return build_project(body.model_dump())


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "model": model_name(), "api_key_configured": bool(os.getenv("PORTKEY_API_KEY", "").strip()),
            "active_run": app.state.active_run, "run_config": default_run_config().name}


def _preset(project_file: str, preset_id: str, label: str) -> dict:
    p = data.project(project_file)
    manifest = data.raw(project_file)
    return {"id": preset_id, "label": label, "name": p.name, "feedstock": data.raw(manifest["feedstock_file"]),
            "economic_assumptions": {k: v.model_dump(mode="json", exclude_none=True) for k, v in p.economic_assumptions.items()}}


@app.get("/api/project")
async def project() -> dict:
    demo = data.project()
    feedstock = json.loads((DATA_DIR / "demo_feedstock.json").read_text(encoding="utf-8"))
    feedstock.pop("about", None)
    return {
        "name": demo.name,
        "presets": [_preset(data.DEMO_PROJECT_FILE, "fictional_demo", "Fictional demo mill"),
                    _preset(data.REFERENCE_PROJECT_FILE, "literature_reference", "Literature-based reference (published data)")],
        "feedstock": feedstock,
        "economic_assumptions": {k: v.model_dump(mode="json", exclude_none=True) for k, v in demo.economic_assumptions.items()},
        "pathways": [demo.evidence.pathway(pid).model_dump() for pid in demo.pathway_ids],
        "scoring": data.scoring_config().model_dump(mode="json"),
        "agents": [{"id": a, "title": AGENT_TITLES[a]} for a in AGENT_ORDER],
    }


@app.get("/api/evidence")
async def evidence() -> dict:
    return data.project().evidence.model_dump(mode="json")


@app.post("/api/preview")
async def preview(body: AssessmentInput) -> dict:
    project = _project(body)
    config = data.scoring_config()
    pathways = []
    for pid in project.pathway_ids:
        analysis = deterministic.economics(project, pid)
        pathways.append({"pathway_id": pid, "name": project.evidence.pathway(pid).name,
                         "compatibility": deterministic.compatibility(project, pid, config).model_dump(mode="json"),
                         "indicative_economics": assess_indicative_economics(analysis, config).model_dump(mode="json"),
                         "scenario_analysis": analysis.model_dump(mode="json")})
    return {"feedstock": {"profile": project.feedstock.model_dump(mode="json"),
                          "normalized": deterministic.normalized_feedstock(project),
                          "checks": deterministic.feedstock_checks(project)},
            "uncertainty_flags": project.uncertainty_flags(), "pathways": pathways}


async def _execute(state: RunState, project) -> None:
    try:
        factory = app.state.model_factory
        result = await run_workflow(project, model=factory() if factory else None, trace=state.trace,
                                    output_dir=app.state.output_dir)
        state.result, state.status = result, result.status
    except Exception as exc:  # e.g. no API key: reported to the dashboard instead of crashing the server
        state.status, state.error = "error", redact(f"{type(exc).__name__}: {exc}")
    finally:
        state.finished_at = now()
        app.state.active_run = None


@app.post("/api/runs", status_code=202)
async def start_run(body: AssessmentInput) -> dict:
    project = _project(body)  # validate first: bad input never starts a run
    if app.state.active_run:
        raise HTTPException(409, f"Run {app.state.active_run} is still going. Wait for it to finish.")
    run_id = new_run_id()
    inputs = body.model_dump()
    state = RunState(run_id=run_id, status="running", started_at=now(), trace=Trace(run_id=run_id, model=model_name()),
                     inputs=inputs)
    if app.state.store_inputs:  # off by default: the inputs stay in memory for this server session only
        runs_dir = app.state.output_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / f"{run_id}.inputs.json").write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
    state.trace.add_agents(list(AGENT_ORDER))
    app.state.runs[run_id] = state
    app.state.active_run = run_id
    task = asyncio.create_task(_execute(state, project))
    app.state.tasks.add(task)  # keep a reference so the task isn't garbage-collected
    task.add_done_callback(app.state.tasks.discard)
    return {"run_id": run_id, "status": "running"}


def _saved(run_id: str) -> FinalAssessment:
    out = app.state.output_dir
    path = out / "latest_assessment.json" if run_id == "latest" else out / "runs" / f"{run_id}.json"
    if not path.exists():
        raise HTTPException(404, "No saved assessment yet. Run the assessment first." if run_id == "latest"
                            else f"Run {run_id} not found.")
    return FinalAssessment.model_validate_json(path.read_text(encoding="utf-8"))


def _saved_response(result: FinalAssessment) -> dict:
    inputs_file = app.state.output_dir / "runs" / f"{result.run_id}.inputs.json"
    inputs = json.loads(inputs_file.read_text(encoding="utf-8")) if inputs_file.exists() else None
    return {"run_id": result.run_id, "status": result.status, "started_at": result.execution.started_at,
            "finished_at": result.execution.finished_at, "error": None, "inputs": inputs,
            "trace": result.execution.model_dump(mode="json"), "result": result.model_dump(mode="json")}


@app.get("/api/runs/latest")
async def latest() -> dict:
    return _saved_response(_saved("latest"))


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    state = app.state.runs.get(run_id)
    if state is None:
        return _saved_response(_saved(run_id))
    return state.model_dump(mode="json")


@app.get("/api/runs/{run_id}/report.{fmt}")
async def report(run_id: str, fmt: Literal["md", "html"]) -> Response:
    state = app.state.runs.get(run_id)
    result = state.result if state and state.result else _saved(run_id)
    body = render_markdown(result) if fmt == "md" else render_html(result)
    media = "text/markdown; charset=utf-8" if fmt == "md" else "text/html; charset=utf-8"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="biovalue-{result.run_id}.{fmt}"'})


# The built dashboard (frontend/dist, committed to the repo) is served from the same server, so running the app needs
# only Python: start uvicorn and open http://127.0.0.1:8765. Registered last, so every /api route above wins.
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
else:
    @app.get("/", include_in_schema=False)
    async def no_dashboard() -> Response:
        return Response("The dashboard build (frontend/dist) is missing. Build it with: npm --prefix frontend install && "
                        "npm --prefix frontend run build. The API itself is running under /api.", media_type="text/plain")
